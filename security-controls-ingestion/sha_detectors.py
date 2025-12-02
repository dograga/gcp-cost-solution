"""Built-in Security Health Analytics Detectors"""

# List of common SHA detectors/categories
# Source: https://cloud.google.com/security-command-center/docs/concepts-vulnerabilities-findings
SHA_DETECTORS = [
    {
        "id": "KMS_PUBLIC_KEY",
        "title": "KMS Public Key",
        "description": "Detects if KMS keys are publicly accessible.",
        "category": "KMS",
        "severity": "HIGH",
        "remediation": "Remove public access from the KMS key.",
        "type": "sha_detector"
    },
    {
        "id": "OPEN_FIREWALL",
        "title": "Open Firewall",
        "description": "Detects firewall rules that allow open access (0.0.0.0/0) to sensitive ports.",
        "category": "Firewall",
        "severity": "HIGH",
        "remediation": "Restrict firewall rules to specific IP ranges.",
        "type": "sha_detector"
    },
    {
        "id": "PUBLIC_BUCKET_ACL",
        "title": "Public Bucket ACL",
        "description": "Detects Cloud Storage buckets that are publicly accessible via ACLs.",
        "category": "Storage",
        "severity": "HIGH",
        "remediation": "Remove public ACLs from the bucket.",
        "type": "sha_detector"
    },
    {
        "id": "PUBLIC_DATASET",
        "title": "Public Dataset",
        "description": "Detects BigQuery datasets that are publicly accessible.",
        "category": "BigQuery",
        "severity": "HIGH",
        "remediation": "Remove public access from the dataset.",
        "type": "sha_detector"
    },
    {
        "id": "SSL_NOT_ENFORCED",
        "title": "SSL Not Enforced",
        "description": "Detects Cloud SQL instances that do not enforce SSL.",
        "category": "SQL",
        "severity": "MEDIUM",
        "remediation": "Enforce SSL connections for the Cloud SQL instance.",
        "type": "sha_detector"
    },
    {
        "id": "MFA_NOT_ENFORCED",
        "title": "MFA Not Enforced",
        "description": "Detects users who do not have Multi-Factor Authentication enabled.",
        "category": "Identity",
        "severity": "HIGH",
        "remediation": "Enforce MFA for all users.",
        "type": "sha_detector"
    },
    {
        "id": "NON_ORG_IAM_MEMBER",
        "title": "Non-Org IAM Member",
        "description": "Detects IAM members that belong to an external organization.",
        "category": "Identity",
        "severity": "MEDIUM",
        "remediation": "Remove external members or whitelist their domains.",
        "type": "sha_detector"
    }
]
