import json
import re


def smart_parse(text: str) -> dict:
    """
    Smart parser that attempts to extract structured data from a string using multiple approaches.
    Handles: pure JSON, JSON embedded in text, key-value pairs, plain text fallback.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r'{.*}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        pattern = re.findall(
            r'(\w+)=["\']([^"\']+)["\']|'
            r'(\w+)=([\w.]+)|'
            r'(\w+):\s*["\']([^"\']+)["\']|'
            r'(\w+):\s*([\w.]+)',
            text)

        if pattern:
            parsed_data = {}
            remaining_str = text
            for match in pattern:
                key = next(m for m in [match[0], match[2], match[4], match[6]] if m)
                value = next(m for m in [match[1], match[3], match[5], match[7]] if m)
                parsed_data[key.lower()] = value
                for possible_format in [f'{key}={value}', f'{key}: {value}', f'{key}="{value}"', f'{key}: "{value}"']:
                    remaining_str = remaining_str.replace(possible_format, '')
            remaining_str = remaining_str.strip().strip(',').strip()
            if remaining_str:
                parsed_data['message'] = remaining_str
            return parsed_data

        return {'message': text}
