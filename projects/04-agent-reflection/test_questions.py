"""
测试问题集 —— 预设问题 + 标准答案
=================================

每个问题都有 ground_truth（标准答案），用于 Ground Truth 评估器自动判分。

问题设计原则（面向"触发反思"）：
    1. 陷阱问题：名字相似的实体（珊瑚城 vs 珊瑚礁堡）容易混淆
    2. 多步链式：需要 3-4 步才能得到答案
    3. 计算题：需要先查数据再计算
    4. 隐含关系：字段值是另一个实体的名字，需要链式 lookup
    5. 对比题：需要查多个实体再比较

难度分级：
    ★☆☆ 简单：1-2 步即可
    ★★☆ 中等：需要 3 步或有轻度混淆风险
    ★★★ 困难：4+ 步或有严重混淆陷阱

为什么这些问题能触发反思？
    - 简单题测试基础能力，Agent 不太会犯错
    - 中等题的"相似名称"陷阱让 Agent 容易用错实体名
    - 困难题的长链式推理让 Agent 容易在某步跳步或混淆
    第一轮犯错后，评估器指出错误，反思器分析原因，
    第二轮 Agent 带着"上次在哪犯错"的记忆重试，避免重蹈覆辙。
"""

from typing import TypedDict


class TestQuestion(TypedDict):
    """测试问题结构。"""
    id: str
    question: str
    ground_truth: str
    difficulty: str  # "easy" | "medium" | "hard"
    category: str  # "lookup" | "chain" | "calculate" | "compare" | "trap"
    description: str  # 问题设计意图说明
    # ground_truth 中包含的关键词列表，用于评估器做模糊匹配
    keywords: list[str]


# ============================================================
# 测试问题集
# ============================================================

TEST_QUESTIONS: list[TestQuestion] = [
    # ── 简单题（★☆☆）：直接查询 ──

    {
        "id": "q01",
        "question": "深渊王国的国王是谁？",
        "ground_truth": "奥西里斯",
        "difficulty": "easy",
        "category": "lookup",
        "description": "单步查询，直接查实体的字段值",
        "keywords": ["奥西里斯"],
    },
    {
        "id": "q02",
        "question": "珊瑚礁堡的人口有多少？",
        "ground_truth": "31000",
        "difficulty": "easy",
        "category": "trap",
        "description": "单步查询，但'珊瑚礁堡'和'珊瑚城'名字相似，Agent 可能错查珊瑚城（82000）",
        "keywords": ["31000"],
    },

    # ── 中等题（★★☆）：多步推理 ──

    {
        "id": "q03",
        "question": "深渊王国国王的导师现在住在哪里？",
        "ground_truth": "暗流洞穴",
        "difficulty": "medium",
        "category": "chain",
        "description": "3步链式：深渊王国国王（奥西里斯）→导师（先知莫拉）→居住地（暗流洞穴）",
        "keywords": ["暗流洞穴"],
    },
    {
        "id": "q04",
        "question": "潮汐帝国的面积是深渊王国的多少倍？请精确到小数点后两位。",
        "ground_truth": "1.25",
        "difficulty": "medium",
        "category": "calculate",
        "description": "查两个面积再计算比值：11500/9200≈1.25",
        "keywords": ["1.25"],
    },
    {
        "id": "q05",
        "question": "珊瑚城和珊瑚礁堡哪个人口更多？多多少？",
        "ground_truth": "珊瑚城人口更多，多51000人",
        "difficulty": "medium",
        "category": "trap",
        "description": "陷阱题：两个名字含'珊瑚'的城市，需要分别准确查询不能混淆",
        "keywords": ["珊瑚城", "51000"],
    },

    # ── 困难题（★★★）：多步 + 陷阱 ──

    {
        "id": "q06",
        "question": "涛涌大帝的导师的导师是谁？此人擅长什么？",
        "ground_truth": "涛涌大帝的导师是海神祭司波塞冬，波塞冬的导师是先知莫拉，先知莫拉擅长预言术与深渊知识",
        "difficulty": "hard",
        "category": "chain",
        "description": "4步链式：涛涌大帝→导师（海神祭司波塞冬）→波塞冬的导师（先知莫拉）→特长",
        "keywords": ["先知莫拉", "预言术"],
    },
    {
        "id": "q07",
        "question": "深海联盟所有国度中人口密度（人口÷面积）最高的是哪个？密度是多少（精确到小数点后两位）？",
        "ground_truth": "珊瑚联邦，人口密度约28.95",
        "difficulty": "hard",
        "category": "calculate",
        "description": "需要查所有国度的面积和人口，逐一计算密度再比较。珊瑚联邦: 220000/7600≈28.95",
        "keywords": ["珊瑚联邦", "28.95"],
    },
    {
        "id": "q08",
        "question": "深渊权杖的拥有者的导师现在住在哪里？",
        "ground_truth": "暗流洞穴",
        "difficulty": "hard",
        "category": "chain",
        "description": "4步链式：深渊权杖→拥有者（奥西里斯）→导师（先知莫拉）→居住地（暗流洞穴）",
        "keywords": ["暗流洞穴"],
    },
    {
        "id": "q09",
        "question": "珊瑚城属于哪个国度？该国度的领导人多大年龄？",
        "ground_truth": "珊瑚城属于珊瑚联邦，议长玛瑞拉89岁",
        "difficulty": "medium",
        "category": "chain",
        "description": "2步链式，'珊瑚城'容易和'珊瑚礁堡'混淆，且珊瑚联邦领导者字段是'议长'而非'国王'",
        "keywords": ["珊瑚联邦", "玛瑞拉", "89"],
    },
    {
        "id": "q10",
        "question": "深海联盟中建国最早的国度是哪个？比建国最晚的早了多少年？",
        "ground_truth": "潮汐帝国建国最早（650年），幽光海域建国最晚（1380年），相差730年",
        "difficulty": "hard",
        "category": "calculate",
        "description": "需要查所有国度的建国年份，找最早和最晚，再算差值",
        "keywords": ["潮汐帝国", "幽光海域", "730"],
    },
]


# ============================================================
# 便捷访问函数
# ============================================================

def get_question_by_id(question_id: str) -> TestQuestion | None:
    """根据 ID 获取测试问题。"""
    for q in TEST_QUESTIONS:
        if q["id"] == question_id:
            return q
    return None


def get_questions_by_difficulty(difficulty: str) -> list[TestQuestion]:
    """根据难度筛选问题。"""
    return [q for q in TEST_QUESTIONS if q["difficulty"] == difficulty]


def get_questions_by_category(category: str) -> list[TestQuestion]:
    """根据类别筛选问题。"""
    return [q for q in TEST_QUESTIONS if q["category"] == category]


def get_demo_questions() -> list[TestQuestion]:
    """
    获取演示用问题（覆盖不同难度和类别）。

    选择标准：
        - 至少一个简单题（验证基础能力）
        - 至少一个陷阱题（验证名称混淆是否触发反思）
        - 至少一个链式题（验证多步推理反思）
        - 至少一个计算题（验证数值错误反思）
        - 至少一个困难题（验证复杂场景反思）
    """
    demo_ids = ["q01", "q04", "q05", "q06", "q10"]
    return [q for q in TEST_QUESTIONS if q["id"] in demo_ids]


# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("测试问题集概览")
    print("=" * 50)

    print(f"\n总问题数：{len(TEST_QUESTIONS)}")

    # 按难度统计
    for diff in ["easy", "medium", "hard"]:
        qs = get_questions_by_difficulty(diff)
        print(f"  {diff}: {len(qs)} 题")

    # 按类别统计
    print("\n按类别：")
    categories = set(q["category"] for q in TEST_QUESTIONS)
    for cat in sorted(categories):
        qs = get_questions_by_category(cat)
        print(f"  {cat}: {len(qs)} 题")

    # 打印所有问题
    print(f"\n{'─' * 50}")
    print("所有问题：")
    for q in TEST_QUESTIONS:
        stars = {"easy": "★☆☆", "medium": "★★☆", "hard": "★★★"}[q["difficulty"]]
        print(f"\n  [{q['id']}] {stars} [{q['category']}]")
        print(f"  Q: {q['question']}")
        print(f"  A: {q['ground_truth']}")
        print(f"  设计：{q['description']}")
