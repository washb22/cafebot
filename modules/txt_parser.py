"""텍스트 파일을 카페 게시 시나리오로 파싱.

포맷:
    제목 : <title>
    ---
    <body multi-line>
    ---
    댓글1 : <text>              # top-level comment (commenter 1)
    ㄴ 작성자 : <text>            # main reply to that comment
    댓글2 : <text>
    ㄴ 작성자 : <text>
    ㄴ 댓글2 : <text>            # commenter 2 replies in same thread
    ㄴ 작성자 : <text>
    ...

출력:
    {
        "title": str,
        "body": str,
        "actions": [
            {"action": "comment", "commenter_num": 1, "text": "..."},
            {"action": "reply", "is_main": True, "to_index": 0, "text": "..."},
            {"action": "reply", "commenter_num": 2, "to_index": 1, "text": "..."},
            ...
        ],
        "commenter_nums": [1, 2, 3, ...]  # 필요한 commenter 번호 목록
    }
"""
import re


COMMENT_RE = re.compile(r'^\s*댓글\s*(\d+)(?:-\d+)?\s*:\s*(.+)$')
AUTHOR_REPLY_RE = re.compile(r'^\s*ㄴ\s*작성자\s*:\s*(.+)$')
COMMENTER_REPLY_RE = re.compile(r'^\s*ㄴ\s*댓글\s*(\d+)(?:-\d+)?\s*:\s*(.+)$')
TITLE_RE = re.compile(r'^\s*제목\s*:\s*(.+)$')


def parse_scenario_text(text):
    """txt 콘텐츠 문자열을 파싱해 시나리오 dict 반환"""
    # 빈줄 정리 + \r 제거
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # --- 기준으로 분할: [title_part, body, comments_part] 형태
    sections = text.split('---')
    if len(sections) < 3:
        raise ValueError("파일 형식 오류: '---' 구분자가 2개 이상 있어야 합니다 (제목/본문/댓글 구분)")

    title_part = sections[0].strip()
    body = sections[1].strip()
    comments_part = '---'.join(sections[2:]).strip()  # 혹시 댓글 안에 --- 있어도 남김

    # 제목 추출
    title_match = TITLE_RE.match(title_part)
    if not title_match:
        raise ValueError("제목을 찾을 수 없습니다. '제목 : ...' 형식이어야 합니다.")
    title = title_match.group(1).strip()

    # 댓글/대댓글 파싱
    actions = []
    commenter_nums = set()
    comments_only = []  # top-level comments in order (for to_index 계산)

    for raw_line in comments_part.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        m = COMMENT_RE.match(line)
        if m:
            num = int(m.group(1))
            content = m.group(2).strip()
            commenter_nums.add(num)
            comments_only.append(num)
            actions.append({
                "action": "comment",
                "commenter_num": num,
                "text": content,
            })
            continue

        m = AUTHOR_REPLY_RE.match(line)
        if m:
            content = m.group(1).strip()
            if not comments_only:
                raise ValueError(f"ㄴ 작성자 답글이 어떤 댓글에 대한 것인지 불명: {line[:40]}")
            actions.append({
                "action": "reply",
                "is_main": True,
                "to_index": len(comments_only) - 1,
                "text": content,
            })
            continue

        m = COMMENTER_REPLY_RE.match(line)
        if m:
            num = int(m.group(1))
            content = m.group(2).strip()
            commenter_nums.add(num)
            if not comments_only:
                raise ValueError(f"ㄴ 댓글{num} 답글이 어떤 댓글에 대한 것인지 불명: {line[:40]}")
            actions.append({
                "action": "reply",
                "is_main": False,
                "commenter_num": num,
                "to_index": len(comments_only) - 1,
                "text": content,
            })
            continue

        # 알 수 없는 줄은 경고 없이 스킵 (파일 여백 등)

    return {
        "title": title,
        "body": body,
        "actions": actions,
        "commenter_nums": sorted(commenter_nums),
    }


def parse_scenario_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return parse_scenario_text(f.read())
