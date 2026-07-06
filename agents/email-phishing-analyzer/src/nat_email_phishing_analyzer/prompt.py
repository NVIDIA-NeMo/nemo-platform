phishing_prompt = """

Examine the following email content and determine if it exhibits signs of malicious intent. Look for any
suspicious signals that may indicate phishing, such as requests for personal information or suspicious tone.

Email content:
{body}

Return your findings as a JSON object with these fields:

- is_likely_phishing: (boolean) true if phishing is suspected
- explanation: (string) detailed explanation of your reasoning

"""
