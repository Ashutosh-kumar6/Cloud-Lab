import re

ERROR_HELP = {
    "SyntaxError": (
        "Python could not understand the way this line is written. Check for a missing "
        "colon (:) after if/for/while/def, a missing closing bracket or quote, or a typo "
        "in a keyword."
    ),
    "IndentationError": (
        "Python uses spaces at the start of a line to know which code belongs together. "
        "After a line ending with a colon, the next line must be indented, and all lines "
        "in the same block must use the same number of spaces."
    ),
    "TabError": (
        "You mixed tabs and spaces for indentation. Use only spaces (4 per level) "
        "everywhere in your program."
    ),
    "TypeError": (
        "You used a value of the wrong type in an operation. A common cause is "
        "adding a number to text, for example 5 + '3'. input() always gives text, so "
        "convert it with int() or float() before doing maths."
    ),
    "ValueError": (
        "A function got the right type of value but the wrong content. A common cause is "
        "int('abc') or int('') on text that is not a whole number. Check what the "
        "input really contains."
    ),
    "ZeroDivisionError": (
        "You divided by zero, which is not possible. Check the number you divide by, and "
        "use an if statement to handle the zero case."
    ),
    "IndexError": (
        "You asked for a position in a list or string that does not exist. Positions start "
        "at 0, so a list with 3 items has positions 0, 1 and 2, not 3."
    ),
    "KeyError": (
        "You looked for a key that is not in the dictionary. Check the spelling of the key, "
        "or use dict.get(key) which does not crash when the key is missing."
    ),
    "AttributeError": (
        "You tried to use a method or property that this kind of value does not have. "
        "Check the spelling of the method name and what type your variable really holds."
    ),
    "ModuleNotFoundError": (
        "Python could not find the module you tried to import. Check the spelling. Only "
        "the standard library is available here, and extra packages are not installed."
    ),
    "ImportError": (
        "Python could not import that name. Check the spelling and that it exists in "
        "the module you import from."
    ),
    "EOFError": (
        "Your program called input() but there was no more input to read. Make sure you "
        "call input() only as many times as the exercise gives you lines."
    ),
    "RecursionError": (
        "A function kept calling itself without stopping. Add a base case that ends "
        "the recursion."
    ),
    "UnboundLocalError": (
        "You used a variable inside a function before giving it a value. Assign the "
        "variable first, or pass it into the function."
    ),
    "FileNotFoundError": (
        "The file you tried to open does not exist. File access is not available in "
        "this lab, so read input with input() instead."
    ),
    "MemoryError": (
        "Your program used more memory than allowed. Look for a loop that keeps "
        "growing a list or string without end."
    ),
}


def _last_line_number(error_text: str):
    matches = re.findall(r'File "/work/main\.py", line (\d+)', error_text)
    return int(matches[-1]) if matches else None


def _error_type_and_message(error_text: str):
    lines = [ln.strip() for ln in error_text.strip().splitlines() if ln.strip()]
    if not lines:
        return None, ""
    match = re.match(r"^([A-Za-z_.]+(?:Error|Exception)):?\s*(.*)$", lines[-1])
    if not match:
        return None, lines[-1]
    return match.group(1).split(".")[-1], match.group(2)


def explain_with_rules(status: str, output: str) -> str:
    if status == "timeout":
        return (
            "Your program ran for too long and was stopped. This usually means a loop that "
            "never ends. Check that the condition of your while loop eventually becomes "
            "False, and that the variable it depends on changes inside the loop. Also check "
            "that you are not waiting for more input() than the exercise provides."
        )

    if status == "failed":
        if "hidden test case" in output:
            return (
                "Your program works on the sample tests but gives a wrong answer on a "
                "hidden test. Think about other kinds of input: zero, negative numbers, "
                "very large numbers, or an empty value. Your logic may only handle the "
                "easy cases."
            )
        return (
            "Your program runs without errors, but its output is different from what "
            "the exercise expects. Compare 'Expected' and 'Got' carefully. Check the "
            "calculation, spelling and capital letters, extra spaces, and whether you "
            "print the right number of lines."
        )

    error_type, message = _error_type_and_message(output)
    if error_type is None:
        return (
            "Your program stopped with an error. Read the last line of the error "
            "message: it names the problem. The line number above it shows where "
            "it happened."
        )

    line_no = _last_line_number(output)
    where = f" It happened on line {line_no} of your code." if line_no else ""

    if error_type == "NameError":
        name_match = re.search(r"name '(.+?)' is not defined", message)
        name = name_match.group(1) if name_match else "a name"
        return (
            f"Python does not know what '{name}' is.{where} Either you never created "
            f"a variable called '{name}', you spelled it differently when you created "
            f"it (capital letters matter), or you used it before giving it a value."
        )

    help_text = ERROR_HELP.get(
        error_type,
        f"Python raised a {error_type}. Read the message after the colon in the last "
        f"line of the error: it says what went wrong.",
    )
    return f"{error_type}: {message}.{where} {help_text}".replace("..", ".")
