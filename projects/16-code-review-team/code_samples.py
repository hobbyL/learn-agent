"""
代码审查团队 —— 虚构代码片段库
================================

4 段有预设问题的 Python 代码,每段代码故意设计了不同维度的问题：
- 代码 A：用户认证模块（安全漏洞）
- 代码 B：数据处理模块（性能问题）
- 代码 C：API 端点（架构问题）
- 代码 D：工具函数（规范问题）

每段代码都标注了预设问题,方便验证审查员是否找到。
"""

# ============================================================
# 代码片段 A：用户认证模块（安全漏洞）
# ============================================================

CODE_A = '''
# user_auth.py
import sqlite3

API_KEY = "FAKE_API_KEY_DO_NOT_USE_IN_PRODUCTION"  # 预设问题：硬编码密钥（P0）

def login(username, password):
    """用户登录验证"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # 预设问题：SQL 注入风险（P0）
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(query)
    user = cursor.fetchone()

    if user:
        # 预设问题：密码明文存储（P0）
        return {"status": "success", "user_id": user[0]}
    return {"status": "failed"}

def reset_password(user_id, new_password):
    """重置密码"""
    # 预设问题：缺少权限校验（P1）
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET password='{new_password}' WHERE id={user_id}")
    conn.commit()
    return True

def get_user_data(user_id):
    """获取用户数据"""
    # 预设问题：未验证输入类型（P1）
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id={user_id}")
    return cursor.fetchone()
'''

# ============================================================
# 代码片段 B：数据处理模块（性能问题）
# ============================================================

CODE_B = '''
# data_processor.py
import time

def process_orders(orders):
    """处理订单列表"""
    results = []

    # 预设问题：O(n²) 嵌套循环（P1）
    for order in orders:
        for item in order['items']:
            # 预设问题：每次循环都计算总价，应提前计算（P2）
            total = sum([i['price'] * i['quantity'] for i in order['items']])

            # 预设问题：阻塞操作在循环内（P1）
            time.sleep(0.1)  # 模拟网络请求

            results.append({
                'order_id': order['id'],
                'item_name': item['name'],
                'total': total
            })

    return results

def find_duplicates(data_list):
    """查找重复项"""
    duplicates = []

    # 预设问题：O(n²) 查找重复（P1），应该用 set
    for i in range(len(data_list)):
        for j in range(i+1, len(data_list)):
            if data_list[i] == data_list[j]:
                duplicates.append(data_list[i])

    return duplicates

def calculate_stats(numbers):
    """计算统计数据"""
    # 预设问题：重复计算，缺少缓存（P2）
    return {
        'mean': sum(numbers) / len(numbers),
        'max': max(numbers),
        'min': min(numbers),
        'sum': sum(numbers),  # sum 被重复计算了
        'count': len(numbers)
    }
'''

# ============================================================
# 代码片段 C：API 端点（架构问题）
# ============================================================

CODE_C = '''
# api_endpoints.py
from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)

@app.route('/api/user/<user_id>', methods=['GET', 'POST', 'DELETE'])
def user_endpoint(user_id):
    """用户API端点"""

    # 预设问题：职责不清，一个函数处理3种操作（P1）
    if request.method == 'GET':
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE id={user_id}")
        user = cursor.fetchone()
        return jsonify(user)

    elif request.method == 'POST':
        data = request.json
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        # 预设问题：没有错误处理（P1）
        cursor.execute(f"UPDATE users SET name='{data['name']}' WHERE id={user_id}")
        conn.commit()
        return jsonify({"status": "updated"})

    elif request.method == 'DELETE':
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM users WHERE id={user_id}")
        conn.commit()
        # 预设问题：没有返回值（P2）

    # 预设问题：缺少默认返回（P1）

@app.route('/api/data', methods=['POST'])
def process_data():
    """数据处理端点"""
    # 预设问题：业务逻辑和API层耦合（P1）
    data = request.json
    result = []
    for item in data:
        # 直接在端点里写业务逻辑
        processed = item['value'] * 2 + 10
        result.append(processed)
    return jsonify(result)
'''

# ============================================================
# 代码片段 D：工具函数（规范问题）
# ============================================================

CODE_D = '''
# utils.py

def f(x,y,z):
    # 预设问题：函数名不清晰（P2）
    # 预设问题：缺少文档字符串（P1）
    # 预设问题：缺少类型注解（P2）
    r=x+y
    r=r*z
    return r

def process(data):
    # 预设问题：缺少文档字符串（P1）
    result=[]
    for i in data:
        # 预设问题：变量名不清晰（P2）
        if i>0:
            result.append(i)
    return result

def calculate_total(items):
    # 预设问题：代码重复，和下面的函数逻辑相同（P1）
    total = 0
    for item in items:
        total += item['price'] * item['quantity']
    return total

def get_order_total(order_items):
    # 预设问题：代码重复（P1）
    sum = 0
    for item in order_items:
        sum += item['price'] * item['quantity']
    return sum

class DataHandler:
    def __init__(self,data):
        # 预设问题：缺少空格（P2）
        self.data=data
        self.result=None

    def Process(self):
        # 预设问题：方法名应该小写（P2）
        # 预设问题：缺少文档字符串（P1）
        self.result=[x*2 for x in self.data]
        return self.result
'''

# ============================================================
# 代码片段元数据
# ============================================================

SAMPLES = {
    "A_user_auth": {
        "code": CODE_A,
        "description": "用户认证模块",
        "file": "user_auth.py",
        "preset_issues": {
            "security": [
                {"line": 5, "severity": "P0", "type": "hardcoded_secret", "desc": "API_KEY 硬编码"},
                {"line": 13, "severity": "P0", "type": "sql_injection", "desc": "SQL 注入风险"},
                {"line": 18, "severity": "P0", "type": "plaintext_password", "desc": "密码明文存储"},
                {"line": 23, "severity": "P1", "type": "missing_auth", "desc": "reset_password 缺少权限校验"},
                {"line": 32, "severity": "P1", "type": "input_validation", "desc": "未验证 user_id 类型"},
            ],
            "performance": [],
            "architecture": [],
            "style": []
        }
    },
    "B_data_processor": {
        "code": CODE_B,
        "description": "数据处理模块",
        "file": "data_processor.py",
        "preset_issues": {
            "security": [],
            "performance": [
                {"line": 9, "severity": "P1", "type": "nested_loop", "desc": "O(n²) 嵌套循环"},
                {"line": 11, "severity": "P2", "type": "redundant_computation", "desc": "循环内重复计算总价"},
                {"line": 14, "severity": "P1", "type": "blocking_io", "desc": "阻塞操作在循环内"},
                {"line": 29, "severity": "P1", "type": "inefficient_search", "desc": "O(n²) 查找重复，应用 set"},
                {"line": 39, "severity": "P2", "type": "missing_cache", "desc": "sum 被重复计算"},
            ],
            "architecture": [],
            "style": []
        }
    },
    "C_api_endpoints": {
        "code": CODE_C,
        "description": "API 端点",
        "file": "api_endpoints.py",
        "preset_issues": {
            "security": [],
            "performance": [],
            "architecture": [
                {"line": 10, "severity": "P1", "type": "mixed_responsibilities", "desc": "一个函数处理3种操作"},
                {"line": 23, "severity": "P1", "type": "no_error_handling", "desc": "缺少错误处理"},
                {"line": 32, "severity": "P2", "type": "missing_return", "desc": "DELETE 没有返回值"},
                {"line": 35, "severity": "P1", "type": "missing_default_return", "desc": "缺少默认返回"},
                {"line": 41, "severity": "P1", "type": "tight_coupling", "desc": "业务逻辑和API层耦合"},
            ],
            "style": []
        }
    },
    "D_utils": {
        "code": CODE_D,
        "description": "工具函数",
        "file": "utils.py",
        "preset_issues": {
            "security": [],
            "performance": [],
            "architecture": [],
            "style": [
                {"line": 3, "severity": "P2", "type": "unclear_name", "desc": "函数名不清晰"},
                {"line": 4, "severity": "P1", "type": "missing_docstring", "desc": "缺少文档字符串"},
                {"line": 5, "severity": "P2", "type": "missing_type_hint", "desc": "缺少类型注解"},
                {"line": 11, "severity": "P1", "type": "missing_docstring", "desc": "process 缺少文档"},
                {"line": 15, "severity": "P2", "type": "unclear_variable", "desc": "变量名 i 不清晰"},
                {"line": 20, "severity": "P1", "type": "code_duplication", "desc": "calculate_total 和 get_order_total 重复"},
                {"line": 32, "severity": "P2", "type": "spacing", "desc": "缺少空格"},
                {"line": 36, "severity": "P2", "type": "naming_convention", "desc": "方法名应该小写"},
                {"line": 37, "severity": "P1", "type": "missing_docstring", "desc": "Process 缺少文档"},
            ]
        }
    }
}


def get_sample(name: str) -> dict:
    """获取指定代码片段"""
    return SAMPLES.get(name)


def get_all_samples() -> dict:
    """获取所有代码片段"""
    return SAMPLES


def get_preset_issues_count() -> dict:
    """统计预设问题数量"""
    counts = {
        "security": 0,
        "performance": 0,
        "architecture": 0,
        "style": 0,
        "total": 0
    }

    for sample in SAMPLES.values():
        for category, issues in sample["preset_issues"].items():
            counts[category] += len(issues)
            counts["total"] += len(issues)

    return counts
