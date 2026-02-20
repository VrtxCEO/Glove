#include "GloveClient.h"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <sstream>
#include <thread>

#ifdef _WIN32
#include <windows.h>
#include <winhttp.h>
#endif

namespace
{
    std::string EscapeJson(const std::string& input)
    {
        std::ostringstream out;
        for (char c : input)
        {
            switch (c)
            {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20)
                {
                    out << ' ';
                }
                else
                {
                    out << c;
                }
                break;
            }
        }
        return out.str();
    }

    std::string FindJsonStringValue(const std::string& json, const std::string& key)
    {
        const std::string needle = "\"" + key + "\"";
        size_t keyPos = json.find(needle);
        if (keyPos == std::string::npos)
        {
            return "";
        }

        size_t colonPos = json.find(':', keyPos + needle.size());
        if (colonPos == std::string::npos)
        {
            return "";
        }

        size_t quoteStart = json.find('"', colonPos + 1);
        if (quoteStart == std::string::npos)
        {
            return "";
        }

        size_t quoteEnd = quoteStart + 1;
        while (quoteEnd < json.size())
        {
            if (json[quoteEnd] == '"' && json[quoteEnd - 1] != '\\')
            {
                break;
            }
            quoteEnd++;
        }

        if (quoteEnd >= json.size())
        {
            return "";
        }

        return json.substr(quoteStart + 1, quoteEnd - quoteStart - 1);
    }

#ifdef _WIN32
    std::wstring Utf8ToWide(const std::string& input)
    {
        if (input.empty())
        {
            return std::wstring();
        }
        int size = MultiByteToWideChar(CP_UTF8, 0, input.c_str(), -1, nullptr, 0);
        if (size <= 0)
        {
            return std::wstring();
        }
        std::wstring out(static_cast<size_t>(size), L'\0');
        MultiByteToWideChar(CP_UTF8, 0, input.c_str(), -1, &out[0], size);
        if (!out.empty() && out.back() == L'\0')
        {
            out.pop_back();
        }
        return out;
    }

    struct ParsedUrl
    {
        std::wstring host;
        INTERNET_PORT port;
        std::wstring path;
        bool secure;
        bool valid;
    };

    ParsedUrl ParseUrl(const std::string& url)
    {
        ParsedUrl result = {L"", 80, L"/", false, false};
        URL_COMPONENTS components;
        ZeroMemory(&components, sizeof(components));
        components.dwStructSize = sizeof(components);
        components.dwSchemeLength = static_cast<DWORD>(-1);
        components.dwHostNameLength = static_cast<DWORD>(-1);
        components.dwUrlPathLength = static_cast<DWORD>(-1);
        components.dwExtraInfoLength = static_cast<DWORD>(-1);

        std::wstring wideUrl = Utf8ToWide(url);
        if (wideUrl.empty())
        {
            return result;
        }

        if (!WinHttpCrackUrl(wideUrl.c_str(), 0, 0, &components))
        {
            return result;
        }

        result.host = std::wstring(components.lpszHostName, components.dwHostNameLength);
        result.port = components.nPort;
        result.secure = components.nScheme == INTERNET_SCHEME_HTTPS;
        result.path = std::wstring(components.lpszUrlPath, components.dwUrlPathLength);
        if (components.dwExtraInfoLength > 0)
        {
            result.path += std::wstring(components.lpszExtraInfo, components.dwExtraInfoLength);
        }
        if (result.path.empty())
        {
            result.path = L"/";
        }
        result.valid = !result.host.empty();
        return result;
    }

    bool HttpRequestWithOptionalBody(
        const std::string& baseUrl,
        const std::string& endpointPath,
        const std::wstring& method,
        const std::string& agentKey,
        int timeoutMs,
        const std::string* body,
        std::string& responseBody)
    {
        ParsedUrl parsed = ParseUrl(baseUrl + endpointPath);
        if (!parsed.valid)
        {
            return false;
        }

        HINTERNET hSession = WinHttpOpen(L"OpenClaw-GloveClient/1.0",
                                         WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                         WINHTTP_NO_PROXY_NAME,
                                         WINHTTP_NO_PROXY_BYPASS,
                                         0);
        if (!hSession)
        {
            return false;
        }

        bool ok = false;
        HINTERNET hConnect = nullptr;
        HINTERNET hRequest = nullptr;

        do
        {
            WinHttpSetTimeouts(hSession, timeoutMs, timeoutMs, timeoutMs, timeoutMs);

            hConnect = WinHttpConnect(hSession, parsed.host.c_str(), parsed.port, 0);
            if (!hConnect)
            {
                break;
            }

            DWORD flags = parsed.secure ? WINHTTP_FLAG_SECURE : 0;
            hRequest = WinHttpOpenRequest(
                hConnect,
                method.c_str(),
                parsed.path.c_str(),
                nullptr,
                WINHTTP_NO_REFERER,
                WINHTTP_DEFAULT_ACCEPT_TYPES,
                flags);
            if (!hRequest)
            {
                break;
            }

            std::wstring contentType = L"Content-Type: application/json\r\n";
            std::wstring keyHeader = L"X-Glove-Agent-Key: " + Utf8ToWide(agentKey) + L"\r\n";
            std::wstring headers = keyHeader;
            if (body)
            {
                headers = contentType + headers;
            }

            BOOL sent = WinHttpSendRequest(
                hRequest,
                headers.c_str(),
                static_cast<DWORD>(-1L),
                body ? (LPVOID)body->data() : WINHTTP_NO_REQUEST_DATA,
                body ? static_cast<DWORD>(body->size()) : 0,
                body ? static_cast<DWORD>(body->size()) : 0,
                0);
            if (!sent)
            {
                break;
            }

            if (!WinHttpReceiveResponse(hRequest, nullptr))
            {
                break;
            }

            std::string response;
            DWORD size = 0;
            do
            {
                size = 0;
                if (!WinHttpQueryDataAvailable(hRequest, &size))
                {
                    break;
                }
                if (size == 0)
                {
                    break;
                }

                std::string buffer(size, '\0');
                DWORD downloaded = 0;
                if (!WinHttpReadData(hRequest, &buffer[0], size, &downloaded))
                {
                    break;
                }
                buffer.resize(downloaded);
                response += buffer;
            } while (size > 0);

            responseBody = response;
            ok = true;
        } while (false);

        if (hRequest)
        {
            WinHttpCloseHandle(hRequest);
        }
        if (hConnect)
        {
            WinHttpCloseHandle(hConnect);
        }
        WinHttpCloseHandle(hSession);
        return ok;
    }

    bool HttpPostJson(
        const std::string& baseUrl,
        const std::string& endpointPath,
        const std::string& agentKey,
        int timeoutMs,
        const std::string& body,
        std::string& responseBody)
    {
        return HttpRequestWithOptionalBody(baseUrl, endpointPath, L"POST", agentKey, timeoutMs, &body, responseBody);
    }

    bool HttpGet(
        const std::string& baseUrl,
        const std::string& endpointPath,
        const std::string& agentKey,
        int timeoutMs,
        std::string& responseBody)
    {
        return HttpRequestWithOptionalBody(baseUrl, endpointPath, L"GET", agentKey, timeoutMs, nullptr, responseBody);
    }
#endif
}

GloveClient::GloveClient(const std::string& baseUrl, const std::string& agentKey, int timeoutMs)
    : m_baseUrl(baseUrl)
    , m_agentKey(agentKey)
    , m_timeoutMs(timeoutMs)
{
}

bool GloveClient::IsConfigured() const
{
    return !m_baseUrl.empty() && !m_agentKey.empty();
}

GloveDecision GloveClient::RequestAction(const std::string& action, const std::string& target, const std::string& metadataJson) const
{
    if (!IsConfigured())
    {
        return {GloveDecisionType::Allow, "glove_not_configured", "", "", "", ""};
    }

    const std::string payload =
        std::string("{\"action\":\"") + EscapeJson(action) +
        "\",\"target\":\"" + EscapeJson(target) +
        "\",\"metadata\":" + metadataJson + "}";

#ifdef _WIN32
    std::string raw;
    if (!HttpPostJson(m_baseUrl, "/api/v1/agent/request", m_agentKey, m_timeoutMs, payload, raw))
    {
        return {GloveDecisionType::Error, "glove_http_error", "", "", "", ""};
    }

    const std::string decision = FindJsonStringValue(raw, "decision");
    GloveDecision out;
    out.reason = FindJsonStringValue(raw, "reason");
    out.policyId = FindJsonStringValue(raw, "policy_id");
    out.risk = FindJsonStringValue(raw, "risk");
    out.requestId = FindJsonStringValue(raw, "request_id");
    out.rawResponse = raw;

    if (decision == "allow")
    {
        out.type = GloveDecisionType::Allow;
    }
    else if (decision == "deny")
    {
        out.type = GloveDecisionType::Deny;
    }
    else if (decision == "require_pin")
    {
        out.type = GloveDecisionType::RequirePin;
    }
    else
    {
        out.type = GloveDecisionType::Error;
        if (out.reason.empty())
        {
            out.reason = "glove_invalid_response";
        }
    }
    return out;
#else
    (void)action;
    (void)target;
    (void)metadataJson;
    return {GloveDecisionType::Allow, "glove_stub_non_windows", "", "", "", ""};
#endif
}

GloveRequestStatus GloveClient::GetRequestStatus(const std::string& requestId) const
{
    if (!IsConfigured() || requestId.empty())
    {
        return GloveRequestStatus::Error;
    }

#ifdef _WIN32
    std::string raw;
    const std::string path = std::string("/api/v1/agent/request-status?request_id=") + requestId;
    if (!HttpGet(m_baseUrl, path, m_agentKey, m_timeoutMs, raw))
    {
        return GloveRequestStatus::Error;
    }

    const std::string status = FindJsonStringValue(raw, "status");
    if (status == "pending")
    {
        return GloveRequestStatus::Pending;
    }
    if (status == "approved")
    {
        return GloveRequestStatus::Approved;
    }
    if (status == "denied")
    {
        return GloveRequestStatus::Denied;
    }
    if (status == "expired")
    {
        return GloveRequestStatus::Expired;
    }
    return GloveRequestStatus::Error;
#else
    (void)requestId;
    return GloveRequestStatus::Error;
#endif
}

GloveRequestStatus GloveClient::WaitForApproval(const std::string& requestId, int maxWaitSeconds, int pollIntervalMs) const
{
    const int maxLoops = (maxWaitSeconds * 1000) / std::max(250, pollIntervalMs);
    for (int i = 0; i < std::max(1, maxLoops); i++)
    {
        GloveRequestStatus status = GetRequestStatus(requestId);
        if (status == GloveRequestStatus::Approved ||
            status == GloveRequestStatus::Denied ||
            status == GloveRequestStatus::Expired)
        {
            return status;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(std::max(250, pollIntervalMs)));
    }
    return GloveRequestStatus::Error;
}
