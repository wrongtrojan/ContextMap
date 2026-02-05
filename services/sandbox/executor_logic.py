import numpy as np
import sympy as sp
import math

def run_calculation(expression, mode="eval", symbol="x"):
    
    # 更加健壮的内置函数提取方式
    if isinstance(__builtins__, dict):
        builtins_dict = __builtins__
    else:
        builtins_dict = vars(__builtins__)

    # 构建安全的命名空间
    allowed_builtins = ['abs', 'min', 'max', 'round', 'len', 'sum', 'float', 'int']
    safe_dict = {
        "np": np, 
        "sp": sp, 
        "math": math,
        "__builtins__": {k: builtins_dict[k] for k in allowed_builtins if k in builtins_dict}
    }

    if mode == "solve":
        # 符号求解
        var = sp.symbols(symbol)
        expr = sp.sympify(expression)
        solution = sp.solve(expr, var)
        # 转换为字符串列表以便传输
        return [str(s) for s in solution]
    
    elif mode == "eval":
        # 数值计算
        result = eval(expression, safe_dict)
        # 处理 numpy 数据类型序列化问题
        if isinstance(result, (np.ndarray, np.generic)):
            return result.tolist()
        return result
    
    else:
        raise ValueError(f"不支持的模式: {mode}")

# 允许独立测试
if __name__ == "__main__":
    try:
        # 测试 A: 符号求解
        test_solve = "x**2 - 4"
        print(f"✅ 独立测试 (solve {test_solve}): {run_calculation(test_solve, mode='solve')}")
        
        # 测试 B: 数值计算
        test_eval = "math.sqrt(16) + np.sin(math.pi/2)"
        print(f"✅ 独立测试 (eval {test_eval}): {run_calculation(test_eval, mode='eval')}")
    except Exception as e:
        print(f"❌ 测试出错: {e}")