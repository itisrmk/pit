"""Query language for searching versions by behavior and metadata."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import List, Optional, Any, Dict, Callable


class Operator(Enum):
    """Comparison operators."""
    EQ = "="
    NE = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    CONTAINS = "contains"
    IN = "in"


class LogicalOp(Enum):
    """Logical operators."""
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class Condition:
    """A single condition in a query."""
    field: str
    operator: Operator
    value: Any

    def __repr__(self) -> str:
        return f"{self.field} {self.operator.value} {self.value}"


@dataclass
class Query:
    """A parsed query."""
    conditions: List[Condition]
    logical_op: LogicalOp = LogicalOp.AND

    def __repr__(self) -> str:
        op = f" {self.logical_op.value.upper()} "
        return op.join(str(c) for c in self.conditions)


class QueryParser:
    """Parse query strings into Query objects."""

    # Field name pattern
    FIELD_PATTERN = r'[a-zA-Z_][a-zA-Z0-9_]*'

    # String value pattern (single or double quoted)
    STRING_PATTERN = r"'[^']*'|\"[^\"]*\""

    # Number value pattern
    NUMBER_PATTERN = r'-?\d+(?:\.\d+)?'

    # Operator pattern
    OPERATOR_PATTERN = r'>=|<=|!=|=|<|>|contains|in'

    def parse(self, query_string: str) -> Query:
        """Parse a query string."""
        query_string = query_string.strip()

        # Detect logical operator
        logical_op = LogicalOp.AND
        if ' OR ' in query_string.upper():
            logical_op = LogicalOp.OR

        # Split by logical operators
        parts = re.split(r'\s+(?:AND|OR)\s+', query_string, flags=re.IGNORECASE)

        conditions = []
        for part in parts:
            part = part.strip()
            if not part:
                continue

            condition = self._parse_condition(part)
            if condition:
                conditions.append(condition)

        return Query(conditions=conditions, logical_op=logical_op)

    def _parse_condition(self, condition_string: str) -> Optional[Condition]:
        """Parse a single condition."""
        # Match: field operator value
        # Handle negation (NOT)
        negate = False
        if condition_string.upper().startswith('NOT '):
            negate = True
            condition_string = condition_string[4:].strip()

        # Find operator
        match = re.search(
            rf'^(?P<field>{self.FIELD_PATTERN})\s*(?P<op>{self.OPERATOR_PATTERN})\s*(?P<value>.+)$',
            condition_string.strip()
        )

        if not match:
            # Try quoted field (for content search)
            match = re.search(
                rf'^"(?P<field>[^"]+)"\s*(?P<op>{self.OPERATOR_PATTERN})\s*(?P<value>.+)$',
                condition_string.strip()
            )

        if not match:
            return None

        field = match.group('field')
        op_str = match.group('op')
        value_str = match.group('value').strip()

        # Parse operator
        operator_map = {
            '=': Operator.EQ,
            '!=': Operator.NE,
            '>': Operator.GT,
            '<': Operator.LT,
            '>=': Operator.GTE,
            '<=': Operator.LTE,
            'contains': Operator.CONTAINS,
            'in': Operator.IN,
        }
        operator = operator_map.get(op_str, Operator.EQ)

        # Parse value
        value = self._parse_value(value_str)

        if negate:
            # Invert operator for NOT
            if operator == Operator.EQ:
                operator = Operator.NE
            elif operator == Operator.NE:
                operator = Operator.EQ

        return Condition(field=field, operator=operator, value=value)

    def _parse_value(self, value_str: str) -> Any:
        """Parse a value string into the appropriate type."""
        value_str = value_str.strip()

        # Check for date in quotes first (YYYY-MM-DD)
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            inner = value_str[1:-1]
            # Try to parse as date
            if re.match(r'^\d{4}-\d{2}-\d{2}$', inner):
                return datetime.strptime(inner, '%Y-%m-%d')
            # Return as regular string
            return inner

        # Number
        if re.match(r'^-?\d+$', value_str):
            return int(value_str)
        if re.match(r'^-?\d+\.\d+$', value_str):
            return float(value_str)

        # Boolean
        if value_str.lower() == 'true':
            return True
        if value_str.lower() == 'false':
            return False

        # List (for 'in' operator)
        if value_str.startswith('[') and value_str.endswith(']'):
            items = value_str[1:-1].split(',')
            return [self._parse_value(item.strip()) for item in items]

        # Date
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value_str):
            return datetime.strptime(value_str, '%Y-%m-%d')

        # Default to string
        return value_str


class QueryExecutor:
    """Execute queries against version data."""

    def __init__(self, versions: List[Any]):
        self.versions = versions

    def execute(self, query: Query) -> List[Any]:
        """Execute a query and return matching versions."""
        results = []

        for version in self.versions:
            if self._matches(version, query):
                results.append(version)

        return results

    def _matches(self, version: Any, query: Query) -> bool:
        """Check if a version matches a query."""
        results = []

        for condition in query.conditions:
            result = self._evaluate_condition(version, condition)
            results.append(result)

        if query.logical_op == LogicalOp.AND:
            return all(results)
        elif query.logical_op == LogicalOp.OR:
            return any(results)
        else:
            return all(results)

    def _evaluate_condition(self, version: Any, condition: Condition) -> bool:
        """Evaluate a single condition against a version."""
        # Get field value
        field_value = self._get_field_value(version, condition.field)

        if field_value is None:
            # Handle null comparisons
            if condition.operator == Operator.EQ:
                return condition.value is None
            elif condition.operator == Operator.NE:
                return condition.value is not None
            return False

        # Evaluate based on operator
        op = condition.operator
        value = condition.value

        if op == Operator.EQ:
            return field_value == value
        elif op == Operator.NE:
            return field_value != value
        elif op == Operator.GT:
            return field_value > value
        elif op == Operator.LT:
            return field_value < value
        elif op == Operator.GTE:
            return field_value >= value
        elif op == Operator.LTE:
            return field_value <= value
        elif op == Operator.CONTAINS:
            if isinstance(field_value, str):
                return value.lower() in field_value.lower()
            elif isinstance(field_value, list):
                return value in field_value
            return False
        elif op == Operator.IN:
            if isinstance(value, list):
                return field_value in value
            return False

        return False

    def _get_field_value(self, version: Any, field: str) -> Any:
        """Get a field value from a version object."""
        # Direct attribute access
        if hasattr(version, field):
            return getattr(version, field)

        # Nested attribute (e.g., 'semantic_diff.summary')
        if '.' in field:
            parts = field.split('.')
            value = version
            for part in parts:
                if value is None:
                    return None
                if isinstance(value, dict):
                    value = value.get(part)
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return None
            return value

        # Content search special case
        if field == 'content':
            if hasattr(version, 'content'):
                return version.content

        return None


class QueryBuilder:
    """Build queries programmatically."""

    def __init__(self):
        self.conditions: List[Condition] = []
        self.logical_op: LogicalOp = LogicalOp.AND

    def where(self, field: str, operator: str, value: Any) -> "QueryBuilder":
        """Add a condition."""
        op_map = {
            '=': Operator.EQ,
            '!=': Operator.NE,
            '>': Operator.GT,
            '<': Operator.LT,
            '>=': Operator.GTE,
            '<=': Operator.LTE,
            'contains': Operator.CONTAINS,
            'in': Operator.IN,
        }
        op = op_map.get(operator, Operator.EQ)
        self.conditions.append(Condition(field=field, operator=op, value=value))
        return self

    def and_(self) -> "QueryBuilder":
        """Set logical operator to AND."""
        self.logical_op = LogicalOp.AND
        return self

    def or_(self) -> "QueryBuilder":
        """Set logical operator to OR."""
        self.logical_op = LogicalOp.OR
        return self

    def build(self) -> Query:
        """Build the query."""
        return Query(conditions=self.conditions, logical_op=self.logical_op)


# Predefined query patterns
class QueryPatterns:
    """Common query patterns."""

    @staticmethod
    def high_success_rate(min_rate: float = 0.9) -> str:
        """Query for versions with high success rate."""
        return f"success_rate >= {min_rate}"

    @staticmethod
    def low_latency(max_ms: int = 500) -> str:
        """Query for versions with low latency."""
        return f"avg_latency_ms < {max_ms}"

    @staticmethod
    def has_tag(tag: str) -> str:
        """Query for versions with a specific tag."""
        return f"tags contains '{tag}'"

    @staticmethod
    def created_after(date: str) -> str:
        """Query for versions created after a date."""
        return f"created_at > '{date}'"

    @staticmethod
    def content_matches(text: str) -> str:
        """Query for versions containing text."""
        return f"content contains '{text}'"

    @staticmethod
    def by_author(author: str) -> str:
        """Query for versions by author."""
        return f"author = '{author}'"
