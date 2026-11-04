"""Export-only wording. Never used for persisted inputs, assessments or audit identity."""
import re


def visitor_text(value):
    if value is None:
        return None
    text = str(value)
    replacements = [
        (r'\bSynthetic data only\s*[;:.]?\s*', ''),
        (r'\b(?:this is|it is) (?:only )?(?:a )?(?:synthetic |simulated )?(?:demo|simulation)\.?', ''),
        (r'\b(?:Demonstration|Demo) only\s*:\s*', ''),
        (r'\((?:synthetic|simulated|demo) data\)', ''),
        (r'\b(?:synthetic|simulated|fictional|fake)(?:\s+demo)?\s+(?:data|information|facts)\b', 'available information'),
        (r'\b(?:synthetic|simulated|fictional|demonstration|demo)\s+', ''),
        (r'\bsynthetic_', ''),
    ]
    for pattern,replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return re.sub(r'[ \t]{2,}', ' ', text).strip()
