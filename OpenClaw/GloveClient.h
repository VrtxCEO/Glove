#pragma once

#include <string>

enum class GloveDecisionType
{
    Allow,
    Deny,
    RequirePin,
    Error
};

enum class GloveRequestStatus
{
    Pending,
    Approved,
    Denied,
    Expired,
    Error
};

struct GloveDecision
{
    GloveDecisionType type;
    std::string reason;
    std::string policyId;
    std::string risk;
    std::string requestId;
    std::string rawResponse;
};

class GloveClient
{
public:
    GloveClient(const std::string& baseUrl, const std::string& agentKey, int timeoutMs = 2000);

    bool IsConfigured() const;

    // Sends action request to Glove agent endpoint.
    // metadataJson must be a valid JSON object literal, e.g. {"source":"openclaw"}.
    GloveDecision RequestAction(const std::string& action, const std::string& target, const std::string& metadataJson) const;
    GloveRequestStatus GetRequestStatus(const std::string& requestId) const;
    GloveRequestStatus WaitForApproval(const std::string& requestId, int maxWaitSeconds = 300, int pollIntervalMs = 2000) const;

private:
    std::string m_baseUrl;
    std::string m_agentKey;
    int m_timeoutMs;
};
