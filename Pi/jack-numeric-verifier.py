"""Bounded numerical Python verifier; NOT a general-purpose Python executor.

Supports arithmetic, assignments, finite range loops, and numeric conditions.
Rejects imports, attributes, subscripts, comprehensions, unbounded loops, arbitrary
function calls, filesystem/network access, and anything outside numerical AST.
"""
from __future__ import annotations

import ast
import math
import operator
import sys

OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
FUNCTIONS = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sum": sum, "len": len, "sqrt": math.sqrt,
    "comb": math.comb, "factorial": math.factorial,
}
MAX_MAGNITUDE = 10**25
MAX_AST_NODES = 1200
MAX_RANGE_ITEMS = 1000
MAX_STEPS = 10000


def bound(value):
    if isinstance(value, bool):
        raise ValueError("Boolean values are not supported")
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)) or abs(value) > MAX_MAGNITUDE:
            raise ValueError("Number exceeds numeric verifier bound")
    elif isinstance(value, (tuple, list)):
        if len(value) > 100:
            raise ValueError("Numeric sequence too long")
        for member in value:
            bound(member)
    else:
        raise ValueError(
            "Only numeric values are permitted in calculations; "
            "literal text labels are allowed only in print(label, number)"
        )
    return value


def number(node, scope):
    if isinstance(node, ast.Constant):
        return bound(node.value)
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        if node.id not in scope:
            raise ValueError("Unknown variable: " + node.id)
        return scope[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
        return bound(UNARY[type(node.op)](number(node.operand, scope)))
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        lhs, rhs = number(node.left, scope), number(node.right, scope)
        if type(node.op) is ast.Pow and abs(rhs) > 40:
            raise ValueError("Exponent exceeds verifier bound")
        return bound(OPS[type(node.op)](lhs, rhs))
    if isinstance(node, (ast.Tuple, ast.List)):
        return bound([number(element, scope) for element in node.elts])
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in FUNCTIONS and not node.keywords):
        args = [number(argument, scope) for argument in node.args]
        if node.func.id in ("comb", "factorial"):
            if any(type(x) is not int or x < 0 or x > 100 for x in args):
                raise ValueError("Combinatorics arguments exceed verifier bounds")
        return bound(FUNCTIONS[node.func.id](*args))
    if isinstance(node, ast.JoinedStr):
        raise ValueError(
            "Formatted strings are unsupported; use print('label:', numeric_expression)"
        )
    raise ValueError("Unsupported Python construct; numeric expressions only")


def numeric_condition(node, scope):
    """Evaluate bounded numeric comparisons, never arbitrary Python truthiness."""
    if isinstance(node, ast.Compare):
        left = number(node.left, scope)
        for op, comparator in zip(node.ops, node.comparators):
            right = number(comparator, scope)
            actions = {
                ast.Lt: operator.lt, ast.LtE: operator.le,
                ast.Gt: operator.gt, ast.GtE: operator.ge,
                ast.Eq: operator.eq, ast.NotEq: operator.ne,
            }
            action = actions.get(type(op))
            if action is None or not action(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(numeric_condition(item, scope) for item in node.values)
        if isinstance(node.op, ast.Or):
            return any(numeric_condition(item, scope) for item in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not numeric_condition(node.operand, scope)
    raise ValueError("Only numeric comparisons are allowed in conditions")


def execute(stmt, scope, outputs, steps):
    steps[0] += 1
    if steps[0] > MAX_STEPS:
        raise ValueError("Numeric verification execution budget exceeded")
    if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and not stmt.targets[0].id.startswith("_")):
        scope[stmt.targets[0].id] = number(stmt.value, scope)
    elif (isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name)
          and not stmt.target.id.startswith("_")
          and type(stmt.op) in OPS):
        name = stmt.target.id
        if name not in scope:
            raise ValueError("Unknown variable: " + name)
        rhs = number(stmt.value, scope)
        if type(stmt.op) is ast.Pow and abs(rhs) > 40:
            raise ValueError("Exponent exceeds verifier bound")
        scope[name] = bound(OPS[type(stmt.op)](scope[name], rhs))
    elif isinstance(stmt, ast.Expr):
        expression = stmt.value
        if (isinstance(expression, ast.Call)
                and isinstance(expression.func, ast.Name)
                and expression.func.id == "print" and not expression.keywords
                and len(expression.args) <= 8):
            displayed = []
            has_numeric = False
            for argument in expression.args:
                # Literal labels are presentation only, not Python values.
                # They must never enter the arithmetic evaluator or scope.
                if (isinstance(argument, ast.Constant)
                        and isinstance(argument.value, str)):
                    label = argument.value
                    if not (1 <= len(label) <= 120 and label.isprintable()):
                        raise ValueError("Print labels must be 1-120 printable characters")
                    displayed.append(label)
                else:
                    displayed.append(str(number(argument, scope)))
                    has_numeric = True
            if not has_numeric:
                raise ValueError("print(...) requires at least one numeric expression")
            outputs.append(" ".join(displayed))
        else:
            outputs.append(str(number(expression, scope)))
    elif (isinstance(stmt, ast.For) and isinstance(stmt.target, ast.Name)
          and not stmt.target.id.startswith("_") and not stmt.orelse
          and isinstance(stmt.iter, ast.Call)
          and isinstance(stmt.iter.func, ast.Name)
          and stmt.iter.func.id == "range" and not stmt.iter.keywords):
        if not 1 <= len(stmt.iter.args) <= 3:
            raise ValueError("range requires one to three numeric arguments")
        args = [number(arg, scope) for arg in stmt.iter.args]
        if any(type(arg) is not int for arg in args):
            raise ValueError("range arguments must be integers")
        sequence = range(*args)
        if len(sequence) > MAX_RANGE_ITEMS:
            raise ValueError("range exceeds numeric verification iteration bound")
        for value in sequence:
            steps[0] += 1
            if steps[0] > MAX_STEPS:
                raise ValueError("Numeric verification execution budget exceeded")
            scope[stmt.target.id] = bound(value)
            for inner in stmt.body:
                execute(inner, scope, outputs, steps)
    elif isinstance(stmt, ast.If):
        chosen = stmt.body if numeric_condition(stmt.test, scope) else stmt.orelse
        for inner in chosen:
            execute(inner, scope, outputs, steps)
    else:
        raise ValueError(
            "Only numeric assignments, expressions, finite for/range loops, "
            "and numeric if comparisons are allowed"
        )
    if sum(len(item) for item in outputs) > 12000:
        raise ValueError("Output limit exceeded")


def evaluate(source):
    if not source or len(source) > 4096:
        raise ValueError("Numeric code must have 1-4096 characters")
    parsed = ast.parse(source, mode="exec")
    if len(list(ast.walk(parsed))) > MAX_AST_NODES:
        raise ValueError("Numerical expression exceeds syntax bound")
    scope = {}
    outputs = []
    steps = [0]
    for stmt in parsed.body:
        execute(stmt, scope, outputs, steps)
    if not outputs:
        raise ValueError("No numerical output produced. Add print(...) to display the calculated result.")
    return "\n".join(outputs)


if __name__ == "__main__":
    try:
        print(evaluate(sys.argv[1] if len(sys.argv) == 2 else ""))
    except (SyntaxError, ArithmeticError, OverflowError, ValueError, TypeError) as exc:
        print("VERIFICATION_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(2)
