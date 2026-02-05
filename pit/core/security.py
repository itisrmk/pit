"""Prompt security scanner for detecting vulnerabilities."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class Severity(Enum):
    """Severity levels for security findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnerabilityCategory(Enum):
    """OWASP LLM Top 10 vulnerability categories."""
    PROMPT_INJECTION = "LLM01"
    DATA_EXFILTRATION = "LLM02"
    SENSITIVE_DATA = "LLM03"
    INSECURE_OUTPUT = "LLM04"

    @property
    def description(self) -> str:
        """Get description for category."""
        descriptions = {
            VulnerabilityCategory.PROMPT_INJECTION: "Prompt Injection",
            VulnerabilityCategory.DATA_EXFILTRATION: "Data Exfiltration",
            VulnerabilityCategory.SENSITIVE_DATA: "Sensitive Data Exposure",
            VulnerabilityCategory.INSECURE_OUTPUT: "Insecure Output Handling",
        }
        return descriptions.get(self, "Unknown")


@dataclass
class SecurityFinding:
    """A security vulnerability finding."""
    category: VulnerabilityCategory
    severity: Severity
    message: str
    line_number: int = 1
    snippet: Optional[str] = None
    recommendation: Optional[str] = None


@dataclass
class ScanResult:
    """Result of a security scan."""
    findings: List[SecurityFinding] = field(default_factory=list)
    risk_score: int = 0

    @property
    def is_valid(self) -> bool:
        """Check if the prompt is valid (no security issues)."""
        return len(self.findings) == 0

    def get_summary(self) -> str:
        """Get a human-readable summary of the scan."""
        if not self.findings:
            return f"✓ No security issues detected (Risk Score: {self.risk_score})"
        
        by_severity = {}
        for f in self.findings:
            sev = f.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
        
        summary = f"⚠ Found {len(self.findings)} security issue(s). Risk Score: {self.risk_score}\n"
        for sev, count in sorted(by_severity.items(), 
                                  key=lambda x: ["critical", "high", "medium", "low", "info"].index(x[0]) if x[0] in ["critical", "high", "medium", "low", "info"] else 99):
            summary += f"  - {sev.upper()}: {count}\n"
        return summary.strip()


class SecurityScanner:
    """Scanner for prompt injection and security vulnerabilities."""

    # Injection patterns
    INJECTION_PATTERNS = [
        (r"ignore\s+(?:previous|above|all)\s+instructions", "Direct instruction override", Severity.CRITICAL),
        (r"disregard\s+(?:previous|above|all)\s+instructions", "Direct instruction override", Severity.CRITICAL),
        (r"forget\s+(?:previous|above|all)\s+instructions", "Direct instruction override", Severity.CRITICAL),
        (r"you\s+are\s+now\s+(?:a|an)\s+", "Role change attempt", Severity.HIGH),
        (r"act\s+as\s+(?:a|an|if\s+you\s+are)", "Role change attempt", Severity.HIGH),
        (r"pretend\s+to\s+be", "Role change attempt", Severity.HIGH),
        (r"```\s*\n\s*system", "System prompt injection", Severity.CRITICAL),
        (r"<\s*system\s*>", "System prompt injection", Severity.CRITICAL),
        (r"\[\s*system\s*\]", "System prompt injection", Severity.CRITICAL),
        (r"\n\s*---\s*\n", "Context delimiter injection", Severity.MEDIUM),
        (r"end\s+of\s+(?:user|human)\s+input", "Context manipulation", Severity.HIGH),
        (r"jailbreak", "Jailbreak attempt", Severity.HIGH),
        (r"DAN\s*\(|Do\s+Anything\s+Now", "Jailbreak pattern", Severity.HIGH),
        (r"developer\s+mode", "Developer mode bypass", Severity.HIGH),
        (r"ignore\s+your\s+(?:ethical|safety|content)\s+guidelines", "Safety bypass", Severity.CRITICAL),
    ]

    # Data leakage patterns
    LEAKAGE_PATTERNS = [
        (r"api[_-]?key\s*[=:]\s*['\"][\w-]+['\"]", "API key exposure", Severity.CRITICAL),
        (r"password\s*[=:]\s*['\"][^'\"]+['\"]", "Password exposure", Severity.CRITICAL),
        (r"secret\s*[=:]\s*['\"][\w-]+['\"]", "Secret exposure", Severity.CRITICAL),
        (r"token\s*[=:]\s*['\"][\w-]+['\"]", "Token exposure", Severity.CRITICAL),
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API key format", Severity.CRITICAL),
        (r"Bearer\s+[a-zA-Z0-9_\-\.]+", "Bearer token exposure", Severity.HIGH),
    ]

    # PII patterns
    PII_PATTERNS = [
        (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "Credit card number", Severity.CRITICAL),
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN pattern", Severity.CRITICAL),
        (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "Email address exposure", Severity.MEDIUM),
    ]

    # Data exfiltration patterns
    EXFILTRATION_PATTERNS = [
        (r"https?://[^\s]+\.(?:com|net|org|io|dev)", "External URL", Severity.LOW),
        (r"send\s+(?:all|the)\s+data\s+to", "Data exfiltration attempt", Severity.HIGH),
    ]

    # Unsafe output patterns
    UNSAFE_OUTPUT_PATTERNS = [
        (r"execute\s+(?:this|the\s+following)\s+code", "Code execution request", Severity.HIGH),
        (r"run\s+(?:this|the\s+following)\s+command", "Command execution request", Severity.HIGH),
        (r"eval\s*\(", "Eval usage", Severity.HIGH),
        (r"exec\s*\(", "Exec usage", Severity.HIGH),
        (r"subprocess", "Subprocess usage", Severity.MEDIUM),
        (r"os\.system", "System command execution", Severity.HIGH),
        (r"__import__", "Dynamic import", Severity.MEDIUM),
        (r"<\s*script", "Script tag injection", Severity.HIGH),
    ]

    def __init__(self):
        """Initialize the security scanner."""
        pass

    def scan(self, content: str, context: str = "user") -> ScanResult:
        """Scan prompt content for security vulnerabilities.

        Args:
            content: The prompt content to scan.
            context: The context of the prompt ("system" or "user").

        Returns:
            ScanResult with findings and risk score.
        """
        findings = []
        lines = content.split("\n")

        # Check injection patterns
        for line_num, line in enumerate(lines, 1):
            line_lower = line.lower()

            for pattern, message, severity in self.INJECTION_PATTERNS:
                if re.search(pattern, line_lower, re.IGNORECASE):
                    findings.append(SecurityFinding(
                        category=VulnerabilityCategory.PROMPT_INJECTION,
                        severity=severity,
                        message=message,
                        line_number=line_num,
                        snippet=line.strip()[:100],
                        recommendation="Validate and sanitize all user inputs. Use input delimiters.",
                    ))

            # Check data leakage
            for pattern, message, severity in self.LEAKAGE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(SecurityFinding(
                        category=VulnerabilityCategory.SENSITIVE_DATA,
                        severity=severity,
                        message=message,
                        line_number=line_num,
                        snippet=line.strip()[:50] + "..." if len(line.strip()) > 50 else line.strip(),
                        recommendation="Remove hardcoded secrets. Use environment variables.",
                    ))

            # Check PII
            for pattern, message, severity in self.PII_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(SecurityFinding(
                        category=VulnerabilityCategory.SENSITIVE_DATA,
                        severity=severity,
                        message=message,
                        line_number=line_num,
                        snippet=line.strip()[:50] + "...",
                    ))

            # Check exfiltration
            for pattern, message, severity in self.EXFILTRATION_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(SecurityFinding(
                        category=VulnerabilityCategory.DATA_EXFILTRATION,
                        severity=severity,
                        message=message,
                        line_number=line_num,
                        snippet=line.strip()[:100],
                    ))

            # Check unsafe output
            for pattern, message, severity in self.UNSAFE_OUTPUT_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(SecurityFinding(
                        category=VulnerabilityCategory.INSECURE_OUTPUT,
                        severity=severity,
                        message=message,
                        line_number=line_num,
                        snippet=line.strip()[:100],
                        recommendation="Validate and sanitize LLM outputs before execution.",
                    ))

        # Calculate risk score
        risk_score = self._calculate_risk_score(findings)

        return ScanResult(findings=findings, risk_score=risk_score)

    def _calculate_risk_score(self, findings: List[SecurityFinding]) -> int:
        """Calculate a risk score based on findings."""
        score = 0
        for finding in findings:
            if finding.severity == Severity.CRITICAL:
                score += 100
            elif finding.severity == Severity.HIGH:
                score += 50
            elif finding.severity == Severity.MEDIUM:
                score += 20
            elif finding.severity == Severity.LOW:
                score += 5
            else:
                score += 1
        return min(score, 1000)  # Cap at 1000

    def validate(self, content: str, min_severity: Severity = Severity.LOW) -> tuple[bool, List[SecurityFinding]]:
        """Validate a prompt against security criteria.

        Args:
            content: The prompt content to validate.
            min_severity: Minimum severity level to consider a failure.

        Returns:
            Tuple of (is_valid, findings)
        """
        result = self.scan(content)
        
        severity_order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        min_index = severity_order.index(min_severity)
        
        # Filter findings at or above min_severity
        significant_findings = [
            f for f in result.findings 
            if severity_order.index(f.severity) >= min_index
        ]
        
        is_valid = len(significant_findings) == 0
        return is_valid, significant_findings
