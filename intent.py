"""
Intent Parser for AirGuard AI system.

Two-stage pipeline:
  1. LLM classification (gpt-4o-mini) — used when OPENAI_API_KEY is set.
     Handles natural language, ambiguous phrasing, and non-English inputs.
  2. Regex fallback — used when LLM is unavailable or returns "unknown".
     Deterministic, zero-latency, no external dependency.

The rest of the system (agent, enforcer, executor) is unchanged.
"""

import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from models import Intent


class IntentParser:
    """
    Parses natural language commands into structured Intent objects.
    
    The parser uses regex patterns to identify action types and extract
    relevant parameters like location, severity, and filenames from
    user commands.
    
    Supported actions:
    - generate_report: Create pollution reports
    - analyze_aqi: Analyze air quality data
    - send_alert: Send pollution alerts
    - shutdown_factory: Shutdown factory operations (blocked by policy)
    - issue_fine: Issue fines to polluters (blocked by policy)
    
    Example:
        >>> parser = IntentParser()
        >>> intent = parser.parse_intent("Generate pollution report for Delhi")
        >>> print(intent.action)
        'generate_report'
        >>> print(intent.parameters)
        {'location': 'Delhi'}
    """
    
    def __init__(self):
        """Initialize the intent parser with action patterns."""
        # Define action patterns with their regex patterns and confidence scores
        self.action_patterns = [
            {
                'action': 'generate_report',
                'patterns': [
                    r'\b(generate|create|make|produce)\s+(a\s+)?(pollution\s+)?report\b',
                    r'\breport\s+(for|about|on)\b',
                    r'\bgenerate\s+pollution\s+report\b',
                    r'\breport\b',
                ],
                'base_confidence': 0.9
            },
            {
                'action': 'analyze_aqi',
                'patterns': [
                    r'\b(analyze|analyse|check|examine|review)\s+(aqi|air\s+quality)\b',
                    r'\b(aqi|air\s+quality)\s+(analysis|check|data)\b',
                    r'\b(analyze|analyse|check)\s+(pollution|air)\b',
                    # Short natural queries: "Delhi pollution", "pollution in Delhi", "Delhi AQI"
                    r'\b(pollution|aqi|air\s+quality)\b',
                ],
                'base_confidence': 0.75
            },
            {
                'action': 'send_alert',
                'patterns': [
                    r'\b(send|issue|broadcast|trigger)\s+(an?\s+)?(info|warning|critical|high|low)?\s*(priority\s+)?alert\b',
                    r'\balert\s+(about|for|regarding)\b',
                    r'\bnotify\s+(about|of)\b'
                ],
                'base_confidence': 0.9
            },
            {
                'action': 'shutdown_factory',
                'patterns': [
                    r'\b(shutdown|shut\s+down|close|stop)\s+(the\s+)?factory\b',
                    r'\bfactory\s+(shutdown|closure)\b',
                    r'\bhalt\s+(factory|production)\b'
                ],
                'base_confidence': 0.95
            },
            {
                'action': 'issue_fine',
                'patterns': [
                    r'\b(issue|impose|levy|give)\s+(a\s+)?fine\b',
                    r'\bfine\s+(for|to)\b',
                    r'\b(penalty|penalize)\b'
                ],
                'base_confidence': 0.95
            },
            # ── New actions ────────────────────────────────────────────────
            {
                'action': 'fetch_live_aqi',
                'patterns': [
                    r'\b(fetch|get|show|live|current|real.?time)\s+(live\s+)?(aqi|air\s+quality)\b',
                    r'\b(what.?s|what\s+is)\s+(the\s+)?(current|live|today.?s)?\s*(aqi|air\s+quality)\b',
                    r'\blive\s+(pollution|aqi|air)\b',
                ],
                'base_confidence': 0.9
            },
            {
                'action': 'compare_cities',
                'patterns': [
                    r'\bcompare\b',
                    r'\b(comparison|versus|vs\.?)\b',
                    r'\bwhich\s+(city|place)\s+(is|has)\s+(better|worse|cleaner|more\s+polluted)\b',
                    r'\brank\s+(cities|pollution|aqi)\b',
                ],
                'base_confidence': 0.9
            },
            {
                'action': 'pollution_trend',
                'patterns': [
                    r'\b(pollution|aqi)\s+trend\b',
                    r'\btrend\s+(of|in|for)\s+(pollution|aqi|air)\b',
                    r'\b(how\s+is|is\s+the)\s+(pollution|aqi|air\s+quality)\s+(trending|changing)\b',
                ],
                'base_confidence': 0.88
            },
            {
                'action': 'health_advisory',
                'patterns': [
                    r'\b(health\s+advisory|health\s+advice|health\s+risk)\b',
                    r'\b(is\s+it\s+safe|safe\s+to\s+(go\s+outside|exercise|run))\b',
                    r'\b(what\s+should\s+i|should\s+i)\s+(wear|do|avoid)\b',
                    r'\bhealth\s+(impact|effect|warning)\b',
                ],
                'base_confidence': 0.88
            },
        ]
        
        # Compile regex patterns for efficiency
        for action_pattern in self.action_patterns:
            action_pattern['compiled_patterns'] = [
                re.compile(pattern, re.IGNORECASE) 
                for pattern in action_pattern['patterns']
            ]
        
        # Parameter extraction patterns
        self.location_pattern = re.compile(
            r'\b(in|for|at|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        )
        self.severity_pattern = re.compile(
            r'\b(info|information|warning|critical|severe|high|low)\b',
            re.IGNORECASE
        )
        self.filename_pattern = re.compile(
            r'\b([a-zA-Z0-9_-]+\.(json|csv|txt|pdf))\b'
        )
    
    def parse_intent(self, command: str) -> Intent:
        """
        Parse a natural language command into a structured Intent object.

        Stage 1 — LLM (if OPENAI_API_KEY is set):
            Calls classify_intent() from llm_intent.py.
            If the LLM returns a confident, known action -> use it.
            Special cases handled here (not routed to executor):
              - "greeting" -> returns a greeting Intent directly
              - "unknown"  -> falls through to regex

        Stage 2 — Regex fallback:
            Original keyword/pattern matching. Always available.

        Parameters are always extracted by the regex layer regardless of
        which stage classified the action.
        """
        if not command or not isinstance(command, str):
            return self._create_error_intent(command, "Empty or invalid command")

        normalized = command.strip()
        if not normalized:
            return self._create_error_intent(command, "Empty command after normalization")

        # ── Stage 1: LLM classification ───────────────────────────────────────
        action, confidence = self._try_llm(normalized)

        # ── Stage 2: Regex fallback if LLM didn't resolve ────────────────────
        if action == "unknown" or action == "error":
            action, confidence = self._match_action(normalized)

        # ── Extract parameters (always regex-based) ───────────────────────────
        parameters = self._extract_parameters(normalized, action)

        return Intent(
            action=action,
            parameters=parameters,
            timestamp=datetime.now(),
            user_command=command,
            confidence=confidence,
        )

    def _try_llm(self, command: str) -> Tuple[str, float]:
        """
        Attempt LLM-based classification.
        Returns ("unknown", 0.0) if LLM is disabled or fails.
        """
        try:
            from llm_intent import classify_intent
            action, confidence = classify_intent(command)
            return action, confidence
        except Exception:
            # Never crash the pipeline due to LLM issues
            return ("unknown", 0.0)
    
    def _match_action(self, command: str) -> Tuple[str, float]:
        """
        Match command against action patterns to identify the action type.
        
        Args:
            command: Normalized command string
            
        Returns:
            Tuple of (action_name, confidence_score)
        """
        best_match = None
        best_confidence = 0.0
        
        for action_pattern in self.action_patterns:
            for compiled_pattern in action_pattern['compiled_patterns']:
                match = compiled_pattern.search(command)
                if match:
                    # Calculate confidence based on match quality
                    confidence = self._calculate_confidence(
                        command, 
                        match, 
                        action_pattern['base_confidence']
                    )
                    
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = action_pattern['action']
        
        # If no match found, return unknown action
        if best_match is None:
            return 'unknown', 0.0
        
        return best_match, best_confidence
    
    def _calculate_confidence(self, command: str, match: re.Match, base_confidence: float) -> float:
        """
        Calculate confidence score based on pattern match quality.
        
        Factors considered:
        - Base confidence of the pattern
        - Match position (earlier matches are better)
        - Match length relative to command length
        
        Args:
            command: The full command string
            match: The regex match object
            base_confidence: Base confidence for this pattern
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Start with base confidence
        confidence = base_confidence
        
        # Adjust based on match position (earlier is better)
        match_position = match.start() / len(command)
        position_bonus = (1.0 - match_position) * 0.05
        confidence = min(1.0, confidence + position_bonus)
        
        # Adjust based on match coverage (longer match relative to command is better)
        match_length = len(match.group(0))
        coverage = match_length / len(command)
        coverage_bonus = coverage * 0.05
        confidence = min(1.0, confidence + coverage_bonus)
        
        return round(confidence, 2)
    
    def _extract_parameters(self, command: str, action: str) -> Dict[str, Any]:
        """
        Extract relevant parameters from command based on action type.
        
        Different actions require different parameters:
        - generate_report: location, filename
        - analyze_aqi: location
        - send_alert: location, severity
        - shutdown_factory: location
        - issue_fine: location
        
        Args:
            command: The command string
            action: The identified action type
            
        Returns:
            Dictionary of extracted parameters
        """
        parameters = {}
        
        # Extract location (common to most actions)
        location = self._extract_location(command)
        if location:
            parameters['location'] = location
        
        # Extract severity and message (for alerts)
        if action == 'send_alert':
            severity = self._extract_severity(command)
            parameters['severity'] = severity if severity else 'warning'
            # Extract message from command (use the command itself as message if not specified)
            parameters['message'] = self._extract_alert_message(command)
        
        # Extract filename (for reports)
        if action == 'generate_report':
            filename = self._extract_filename(command)
            if filename:
                parameters['filename'] = filename

        # Extract cities list for compare_cities
        if action == 'compare_cities':
            cities = self._extract_cities(command)
            if cities:
                parameters['cities'] = cities

        return parameters
    
    def _extract_location(self, command: str) -> Optional[str]:
        """
        Extract location from command.
        
        Looks for patterns like "in Delhi", "for Mumbai", "at Bangalore".
        
        Args:
            command: The command string
            
        Returns:
            Location string or None if not found
        """
        match = self.location_pattern.search(command)
        if match:
            return match.group(2)
        
        # Try to find capitalized words that might be locations
        # Common Indian cities
        cities = ['Delhi', 'Mumbai', 'Bangalore', 'Chennai', 'Kolkata', 
                  'Hyderabad', 'Pune', 'Ahmedabad', 'Jaipur', 'Lucknow',
                  'Mayapuri', 'Noida', 'Gurgaon']
        
        for city in cities:
            if city.lower() in command.lower():
                return city
        
        return None
    
    def _extract_severity(self, command: str) -> Optional[str]:
        """
        Extract severity level from command.
        
        Maps various severity terms to standard levels: info, warning, critical.
        
        Args:
            command: The command string
            
        Returns:
            Severity level or None if not found
        """
        match = self.severity_pattern.search(command)
        if match:
            severity_text = match.group(1).lower()
            
            # Map to standard severity levels
            if severity_text in ['info', 'information', 'low']:
                return 'info'
            elif severity_text in ['warning']:
                return 'warning'
            elif severity_text in ['critical', 'severe', 'high']:
                return 'critical'
        
        return None
    
    def _extract_filename(self, command: str) -> Optional[str]:
        """
        Extract filename from command.
        
        Looks for patterns like "report.pdf", "delhi_data.json".
        
        Args:
            command: The command string
            
        Returns:
            Filename or None if not found
        """
        match = self.filename_pattern.search(command)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_alert_message(self, command: str) -> str:
        """
        Extract alert message from command.
        
        Extracts the message content from alert commands, removing the action keywords.
        
        Args:
            command: The command string
            
        Returns:
            Alert message string
        """
        # Remove common alert keywords to get the message
        message = command
        
        # Remove action keywords
        keywords_to_remove = [
            r'\b(send|issue|broadcast|trigger)\s+(an?\s+)?',
            r'\b(info|warning|critical|high|low)?\s*(priority\s+)?alert\s+(about|for|regarding)?\s*',
            r'\balert\s+(about|for|regarding)\s*',
            r'\bnotify\s+(about|of)\s*'
        ]
        
        for keyword_pattern in keywords_to_remove:
            message = re.sub(keyword_pattern, '', message, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        message = ' '.join(message.split())
        
        # If message is empty or too short, use a default
        if not message or len(message) < 5:
            location = self._extract_location(command)
            if location:
                message = f"High pollution levels detected in {location}"
            else:
                message = "High pollution levels detected"
        
        return message.strip()
    
    def _extract_cities(self, command: str) -> list:
        """
        Extract multiple city names from a compare command.
        Returns a list of matched city names (2+ for a meaningful comparison).
        """
        known_cities = [
            'Delhi', 'Mumbai', 'Bangalore', 'Chennai', 'Kolkata',
            'Hyderabad', 'Pune', 'Ahmedabad', 'Jaipur', 'Lucknow',
            'Noida', 'Gurgaon',
        ]
        found = [c for c in known_cities if c.lower() in command.lower()]
        return found if len(found) >= 2 else found

    def _create_error_intent(self, command: str, error_message: str) -> Intent:
        """
        Create an error intent for invalid or unparseable commands.
        
        Args:
            command: The original command (may be invalid)
            error_message: Description of the error
            
        Returns:
            Intent object with action='error' and error details
        """
        return Intent(
            action='error',
            parameters={'error': error_message, 'original_command': command},
            timestamp=datetime.now(),
            user_command=command if command else '',
            confidence=0.0
        )
    
    def validate_intent_structure(self, intent: Intent) -> bool:
        """
        Validate that an intent has the required structure and fields.
        
        Checks:
        - Intent is not None
        - Action is non-empty string
        - Parameters is a dictionary
        - Timestamp is valid
        - Confidence is between 0.0 and 1.0
        
        Args:
            intent: Intent object to validate
            
        Returns:
            True if intent is valid, False otherwise
        """
        if intent is None:
            return False
        
        try:
            # Check action
            if not intent.action or not isinstance(intent.action, str):
                return False
            
            # Check parameters
            if not isinstance(intent.parameters, dict):
                return False
            
            # Check timestamp
            if not isinstance(intent.timestamp, datetime):
                return False
            
            # Check confidence
            if not isinstance(intent.confidence, (int, float)):
                return False
            
            if not (0.0 <= intent.confidence <= 1.0):
                return False
            
            # Check user_command
            if not isinstance(intent.user_command, str):
                return False
            
            return True
            
        except (AttributeError, TypeError):
            return False
