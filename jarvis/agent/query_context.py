"""Separate supported client formatting instructions from the retrieval query."""

import unicodedata


# go-cqhttp appends this fixed suffix to Chat and Generate requests.
_QQ_OUTPUT_SUFFIX = """

QQ输出约束：
返回适合直接发送到QQ的普通文本。
可以使用emoji和普通中文标点、普通符号突出标题和重点。
不允许使用Markdown格式，不要使用Markdown标题、项目符号、加粗、斜体、删除线、代码块、表格、引用或Markdown链接。
可以用简短自然段组织内容。"""

_GREETINGS = frozenset({
    "你好", "您好", "你们好", "大家好", "嗨", "哈喽", "哈啰", "嘿",
    "早上好", "早安", "上午好", "中午好", "下午好", "晚上好",
    "hi", "hello", "hey", "hi there", "hello there", "good morning",
    "good afternoon", "good evening",
})


def retrieval_query(query: str, user_id: str) -> str:
    if user_id.startswith(("qq:private:", "qq:group:")):
        query = query.removesuffix(_QQ_OUTPUT_SUFFIX)
    return query.strip()


def is_standalone_greeting(query: str) -> bool:
    query = unicodedata.normalize("NFKC", query).casefold()
    query = " ".join(query.split()).strip(" !?.,。…~、")
    return query in _GREETINGS
