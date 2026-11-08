"""Bounded numerical Python verifier; NOT a general-purpose Python executor.

Reject imports, attribute access, subscripts, comprehensions, loops, arbitrary
function calls, filesystem/network access and anything outside numerical AST.
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
        raise ValueError("Only numeric values are permitted")
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
    raise ValueError("Unsupported Python construct; numeric expressions only")


def evaluate(source):
    if not source or len(source) > 4096:
        raise ValueError("Numeric code must have 1-4096 characters")
    parsed = ast.parse(source, mode="exec")
    if len(list(ast.walk(parsed))) > 200:
        raise ValueError("Numerical expression exceeds syntax bound")
    scope = {}
    outputs = []
    for stmt in parsed.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and not stmt.targets[0].id.startswith("_")):
            scope[stmt.targets[0].id] = number(stmt.value, scope)
        elif isinstance(stmt, ast.Expr):
            expression = stmt.value
            if (isinstance(expression, ast.Call) and
                    isinstance(expression.func, ast.Name) and
                    expression.func.id == "print" and not expression.keywords
                    and len(expression.args) <= 8):
                outputs.append(" ".join(str(number(v, scope)) for v in expression.args))
            else:
                outputs.append(str(number(expression, scope)))
        else:
            raise ValueError("Only numeric assignments and expressions are allowed")
        if sum(len(item) for item in outputs) > 12000:
            raise ValueError("Output limit exceeded")
    return "\n".join(outputs) if outputs else "No result; add print(...) to output values"


if __name__ == "__main__":
    try:
        print(evaluate(sys.argv[1] if len(sys.argv) == 2 else ""))
    except (SyntaxError, ArithmeticError, OverflowError, ValueError, TypeError) as exc:
        print("VERIFICATION_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(2)
