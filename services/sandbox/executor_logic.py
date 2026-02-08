import numpy as np
import sympy as sp
import math

def run_calculation(expression, mode="eval", symbol="x"):
    
    if isinstance(__builtins__, dict):
        builtins_dict = __builtins__
    else:
        builtins_dict = vars(__builtins__)

    allowed_builtins = ['abs', 'min', 'max', 'round', 'len', 'sum', 'float', 'int']
    safe_dict = {
        "np": np, 
        "sp": sp, 
        "math": math,
        "__builtins__": {k: builtins_dict[k] for k in allowed_builtins if k in builtins_dict}
    }

    if mode == "solve":
        var = sp.symbols(symbol)
        expr = sp.sympify(expression)
        solution = sp.solve(expr, var)
        return [str(s) for s in solution]
    
    elif mode == "eval":
        result = eval(expression, safe_dict)
        if isinstance(result, (np.ndarray, np.generic)):
            return result.tolist()
        return result
    
    else:
        raise ValueError(f"Unsupported modality: {mode}")

if __name__ == "__main__":
    try:
        import sys
        import json

        input_json = sys.argv[1] if len(sys.argv) > 1 else "{}"
        params = json.loads(input_json)
        
        expression = params.get("expression", "")
        mode = params.get("mode", "eval")
        symbol = params.get("symbol", "x")

        result = run_calculation(expression, mode, symbol)

        sys.stdout.write(json.dumps({"status": "success", "result": result}, ensure_ascii=False) + '\n')
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Wrapper entry point crash: {str(e)}"}))