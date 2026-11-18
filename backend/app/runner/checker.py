def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def is_correct(actual: str, expected: str) -> bool:
    return normalize(actual) == normalize(expected)
