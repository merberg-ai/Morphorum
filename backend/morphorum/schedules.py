from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduleKeyframe:
    frame: int
    expression: str
    frame_expression: str


@dataclass(frozen=True)
class PromptTransition:
    mode: str
    from_frame: int
    from_text: str
    to_frame: int
    to_text: str
    from_weight: float
    to_weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "from_frame": self.from_frame,
            "from_text": self.from_text,
            "to_frame": self.to_frame,
            "to_text": self.to_text,
            "from_weight": self.from_weight,
            "to_weight": self.to_weight,
        }


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _lerp(a: float, b: float, amount: float) -> float:
    return a + (b - a) * amount


def _where(condition: Any, when_true: Any, when_false: Any) -> Any:
    return when_true if condition else when_false


_ALLOWED_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "sqrt": math.sqrt,
    "abs": abs,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
    "radians": math.radians,
    "degrees": math.degrees,
    "clamp": _clamp,
    "lerp": _lerp,
    "where": _where,
}

_ALLOWED_NAMES = {
    "pi": math.pi,
    "e": math.e,
}


class _ExpressionEvaluator(ast.NodeVisitor):
    def __init__(self, variables: dict[str, float]) -> None:
        self.variables = variables

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, bool):
            return node.value
        if isinstance(node.value, (int, float)):
            return node.value
        raise ScheduleError("Only numeric constants are allowed in schedule expressions.")

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.variables:
            return self.variables[node.id]
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        raise ScheduleError(f"Unknown schedule variable '{node.id}'.")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            exponent = float(right)
            if abs(exponent) > 64:
                raise ScheduleError("Schedule exponent is too large.")
            return left**right
        raise ScheduleError("Unsupported schedule operator.")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        value = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +value
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.Not):
            return not value
        raise ScheduleError("Unsupported unary schedule operator.")

    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        values = [bool(self.visit(value)) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        raise ScheduleError("Unsupported boolean schedule operator.")

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for operator, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if isinstance(operator, ast.Lt):
                result = left < right
            elif isinstance(operator, ast.LtE):
                result = left <= right
            elif isinstance(operator, ast.Gt):
                result = left > right
            elif isinstance(operator, ast.GtE):
                result = left >= right
            elif isinstance(operator, ast.Eq):
                result = left == right
            elif isinstance(operator, ast.NotEq):
                result = left != right
            else:
                raise ScheduleError("Unsupported schedule comparison.")
            if not result:
                return False
            left = right
        return True

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        return self.visit(node.body if self.visit(node.test) else node.orelse)

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ScheduleError("Schedule functions must be called by name.")
        function = _ALLOWED_FUNCTIONS.get(node.func.id)
        if function is None:
            raise ScheduleError(f"Unknown schedule function '{node.func.id}'.")
        if node.keywords:
            raise ScheduleError("Keyword arguments are not allowed in schedule functions.")
        arguments = [self.visit(argument) for argument in node.args]
        try:
            return function(*arguments)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ScheduleError(
                f"Could not evaluate schedule function '{node.func.id}': {exc}"
            ) from exc

    def generic_visit(self, node: ast.AST) -> Any:
        raise ScheduleError(
            f"Unsupported syntax in schedule expression: {type(node).__name__}."
        )


def evaluate_expression(
    expression: str,
    *,
    t: float,
    max_f: float,
    seed: float = 0,
    fps: float = 24,
    variables: dict[str, float] | None = None,
) -> float:
    source = str(expression or "").strip()
    if not source:
        raise ScheduleError("Schedule expression is empty.")

    context = {
        "t": float(t),
        "f": float(t),
        "max_f": float(max_f),
        "s": float(seed),
        "seed": float(seed),
        "fps": float(fps),
        "pw_a": 0.0,
        "pw_b": 0.0,
        "pw_c": 0.0,
        "pw_d": 0.0,
    }
    if variables:
        for key, value in variables.items():
            if isinstance(key, str) and key.isidentifier():
                context[key] = float(value)

    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise ScheduleError(f"Invalid schedule expression '{source}': {exc.msg}.") from exc

    try:
        value = _ExpressionEvaluator(context).visit(tree)
        number = float(value)
    except ScheduleError:
        raise
    except (ArithmeticError, TypeError, ValueError, OverflowError) as exc:
        raise ScheduleError(f"Could not evaluate schedule expression '{source}': {exc}") from exc

    if not math.isfinite(number):
        raise ScheduleError(f"Schedule expression '{source}' produced a non-finite value.")
    return number


def _find_top_level_colon(text: str, start: int) -> int:
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == ":":
            return index
    return -1


def _read_balanced_parentheses(text: str, start: int) -> tuple[str, int]:
    if start >= len(text) or text[start] != "(":
        raise ScheduleError("Expected '(' after schedule frame.")
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
            if depth < 0:
                break
    raise ScheduleError("Schedule expression has unbalanced parentheses.")


def _normalize_frame_expression(value: str) -> str:
    expression = str(value or "").strip()
    if (
        len(expression) >= 2
        and expression[0] == expression[-1]
        and expression[0] in {"'", '"'}
    ):
        expression = expression[1:-1].strip()
    if not expression:
        raise ScheduleError("Schedule frame expression is empty.")
    return expression


def parse_schedule(
    schedule: str,
    *,
    max_frames: int,
    seed: int = 0,
    fps: float = 24,
) -> list[ScheduleKeyframe]:
    text = str(schedule or "").strip()
    if not text:
        raise ScheduleError("Schedule is empty.")
    if max_frames < 1:
        raise ScheduleError("max_frames must be at least 1.")

    max_f = max_frames - 1
    position = 0
    parsed: dict[int, ScheduleKeyframe] = {}

    while position < len(text):
        while position < len(text) and (text[position].isspace() or text[position] == ","):
            position += 1
        if position >= len(text):
            break

        colon = _find_top_level_colon(text, position)
        if colon < 0:
            raise ScheduleError(f"Expected ':' after schedule frame near '{text[position:]}'.")
        frame_source = _normalize_frame_expression(text[position:colon])

        cursor = colon + 1
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        expression, cursor = _read_balanced_parentheses(text, cursor)
        expression = expression.strip()
        if not expression:
            raise ScheduleError(f"Schedule value for frame '{frame_source}' is empty.")

        frame_value = evaluate_expression(
            frame_source,
            t=0,
            max_f=max_f,
            seed=seed,
            fps=fps,
        )
        frame = int(round(frame_value))
        if abs(frame_value - frame) > 1e-6:
            raise ScheduleError(
                f"Schedule frame expression '{frame_source}' resolved to non-integer {frame_value:g}."
            )
        if frame < 0:
            raise ScheduleError(
                f"Schedule frame expression '{frame_source}' resolved below frame zero."
            )

        parsed[frame] = ScheduleKeyframe(
            frame=frame,
            expression=expression,
            frame_expression=frame_source,
        )

        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text):
            if text[cursor] != ",":
                raise ScheduleError(
                    f"Expected ',' after schedule value near '{text[cursor:]}'."
                )
            cursor += 1
        position = cursor

    if not parsed:
        raise ScheduleError("Schedule contains no keyframes.")
    return [parsed[frame] for frame in sorted(parsed)]


def _expression_value(
    keyframe: ScheduleKeyframe,
    *,
    frame: int,
    max_frames: int,
    seed: int,
    fps: float,
    variables: dict[str, float] | None,
) -> float:
    return evaluate_expression(
        keyframe.expression,
        t=frame,
        max_f=max_frames - 1,
        seed=seed,
        fps=fps,
        variables=variables,
    )


def resolve_numeric_schedule(
    schedule: str,
    *,
    frame: int,
    max_frames: int,
    seed: int = 0,
    fps: float = 24,
    interpolation: str = "linear",
    variables: dict[str, float] | None = None,
) -> float:
    if max_frames < 1:
        raise ScheduleError("max_frames must be at least 1.")
    if frame < 0 or frame >= max_frames:
        raise ScheduleError(
            f"Frame {frame} is outside the animation range 0..{max_frames - 1}."
        )

    keyframes = parse_schedule(
        schedule,
        max_frames=max_frames,
        seed=seed,
        fps=fps,
    )

    mode = str(interpolation or "linear").strip().lower()
    if mode not in {"linear", "hold"}:
        raise ScheduleError(f"Unsupported schedule interpolation mode '{interpolation}'.")

    previous = keyframes[0]
    following = keyframes[-1]

    for keyframe in keyframes:
        if keyframe.frame <= frame:
            previous = keyframe
        if keyframe.frame >= frame:
            following = keyframe
            break

    if frame <= keyframes[0].frame:
        return _expression_value(
            keyframes[0],
            frame=frame,
            max_frames=max_frames,
            seed=seed,
            fps=fps,
            variables=variables,
        )
    if frame >= keyframes[-1].frame:
        return _expression_value(
            keyframes[-1],
            frame=frame,
            max_frames=max_frames,
            seed=seed,
            fps=fps,
            variables=variables,
        )

    previous_value = _expression_value(
        previous,
        frame=frame,
        max_frames=max_frames,
        seed=seed,
        fps=fps,
        variables=variables,
    )

    if mode == "hold" or previous.frame == following.frame:
        return previous_value

    following_value = _expression_value(
        following,
        frame=frame,
        max_frames=max_frames,
        seed=seed,
        fps=fps,
        variables=variables,
    )
    amount = (frame - previous.frame) / (following.frame - previous.frame)
    return _lerp(previous_value, following_value, amount)


def _normalized_prompt_map(value: Any, max_frames: int) -> list[tuple[int, str]]:
    source = value if isinstance(value, dict) else {}
    prompts: dict[int, str] = {}
    for raw_frame, raw_text in source.items():
        try:
            frame = int(str(raw_frame).strip())
        except (TypeError, ValueError):
            continue
        if 0 <= frame < max_frames:
            prompts[frame] = str(raw_text or "")
    if not prompts:
        prompts[0] = ""
    elif 0 not in prompts:
        prompts[0] = ""
    return sorted(prompts.items())


def resolve_prompt_transition(
    prompts: dict[str, str] | None,
    *,
    frame: int,
    max_frames: int,
    mode: str = "blend",
) -> PromptTransition:
    if frame < 0 or frame >= max_frames:
        raise ScheduleError(
            f"Frame {frame} is outside the animation range 0..{max_frames - 1}."
        )

    items = _normalized_prompt_map(prompts, max_frames)
    transition_mode = str(mode or "blend").strip().lower()
    if transition_mode not in {"blend", "hold"}:
        raise ScheduleError(f"Unsupported prompt transition mode '{mode}'.")

    previous = items[0]
    following = items[-1]
    for item in items:
        if item[0] <= frame:
            previous = item
        if item[0] >= frame:
            following = item
            break

    if previous[0] == following[0] or transition_mode == "hold":
        return PromptTransition(
            mode=transition_mode,
            from_frame=previous[0],
            from_text=previous[1],
            to_frame=following[0],
            to_text=following[1],
            from_weight=1.0,
            to_weight=0.0,
        )

    amount = (frame - previous[0]) / (following[0] - previous[0])
    return PromptTransition(
        mode=transition_mode,
        from_frame=previous[0],
        from_text=previous[1],
        to_frame=following[0],
        to_text=following[1],
        from_weight=1.0 - amount,
        to_weight=amount,
    )


def validate_numeric_schedule(
    schedule: str,
    *,
    max_frames: int,
    seed: int = 0,
    fps: float = 24,
    interpolation: str = "linear",
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    try:
        keyframes = parse_schedule(
            schedule,
            max_frames=max_frames,
            seed=seed,
            fps=fps,
        )
    except ScheduleError as exc:
        return {
            "valid": False,
            "issues": [{"severity": "error", "message": str(exc)}],
            "keyframes": [],
        }

    for keyframe in keyframes:
        if keyframe.frame >= max_frames:
            issues.append(
                {
                    "severity": "warning",
                    "frame": keyframe.frame,
                    "message": (
                        f"Keyframe {keyframe.frame} is outside the current animation "
                        f"range 0..{max_frames - 1}."
                    ),
                }
            )

    probe_frames = {0, max_frames - 1}
    probe_frames.update(
        keyframe.frame for keyframe in keyframes if 0 <= keyframe.frame < max_frames
    )
    for left, right in zip(keyframes, keyframes[1:]):
        if right.frame > left.frame:
            midpoint = (left.frame + right.frame) // 2
            if 0 <= midpoint < max_frames:
                probe_frames.add(midpoint)

    for probe in sorted(probe_frames):
        try:
            resolve_numeric_schedule(
                schedule,
                frame=probe,
                max_frames=max_frames,
                seed=seed,
                fps=fps,
                interpolation=interpolation,
            )
        except ScheduleError as exc:
            issues.append(
                {
                    "severity": "error",
                    "frame": probe,
                    "message": str(exc),
                }
            )
            break

    return {
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "issues": issues,
        "keyframes": [
            {
                "frame": keyframe.frame,
                "frame_expression": keyframe.frame_expression,
                "expression": keyframe.expression,
            }
            for keyframe in keyframes
        ],
    }


def sample_schedule(
    schedule: str,
    *,
    max_frames: int,
    seed: int = 0,
    fps: float = 24,
    interpolation: str = "linear",
    sample_count: int = 120,
) -> list[dict[str, float | int]]:
    count = max(2, min(int(sample_count), 500))
    if max_frames <= count:
        frames: Iterable[int] = range(max_frames)
    else:
        last = max_frames - 1
        frames = sorted(
            {
                int(round(index * last / (count - 1)))
                for index in range(count)
            }
        )

    return [
        {
            "frame": frame,
            "value": resolve_numeric_schedule(
                schedule,
                frame=frame,
                max_frames=max_frames,
                seed=seed,
                fps=fps,
                interpolation=interpolation,
            ),
        }
        for frame in frames
    ]
