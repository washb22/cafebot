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
    """txt 콘텐츠 문자열을 파싱해 시나리오 dict 반환.

    두 가지 형식 지원:
    1) 풀 시나리오: '제목:' + '---' + 본문 + '---' + 댓글... (글 작성+댓글)
    2) 댓글 전용:  '---' 구분자 없이 '댓글N:' 줄만 나열 (이미 있는 글에 댓글만 달기)
    """
    # 빈줄 정리 + \r 제거
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # 구버전 [댓글차단] 마커 (v1.4 잠깐 도입 후 제거됨) — 댓글 본문에 섞이지 않도록 무음 제거.
    # v1.5 부터 UI 체크박스로 옮겨졌으므로 여기서는 단순 strip.
    text = re.sub(r'^\s*\[\s*댓글\s*차단\s*\]\s*$', '', text, flags=re.MULTILINE)

    # --- 기준으로 분할
    sections = text.split('---')

    if len(sections) >= 3:
        # 풀 시나리오 모드
        title_part = sections[0].strip()
        body = sections[1].strip()
        comments_part = '---'.join(sections[2:]).strip()

        title_match = TITLE_RE.match(title_part)
        if not title_match:
            raise ValueError("제목을 찾을 수 없습니다. '제목 : ...' 형식이어야 합니다.")
        title = title_match.group(1).strip()
    else:
        # 댓글 전용 모드: 전체를 comments_part 로 취급, 제목/본문은 빈값
        title = ""
        body = ""
        comments_part = text.strip()

        # 유효성: 댓글 줄이 하나라도 있는지
        has_comment_line = any(
            COMMENT_RE.match(ln) or AUTHOR_REPLY_RE.match(ln) or COMMENTER_REPLY_RE.match(ln)
            for ln in comments_part.split('\n')
        )
        if not has_comment_line:
            raise ValueError(
                "댓글 형식을 찾을 수 없습니다. 풀 시나리오는 '제목:' + '---' + 본문 + '---' + 댓글 형식, "
                "댓글 전용은 '댓글1: ...' 줄만 나열하세요."
            )

    # 본문 내 이미지 마커 수집 — [이미지1], [이미지2], ... 등
    image_marker_re = re.compile(r'\[이미지(\d+)\]')
    image_nums = sorted({int(m) for m in image_marker_re.findall(body)})

    # 댓글/대댓글 파싱 (여러 줄 본문 지원: 마커 없는 줄은 직전 action 에 이어붙임)
    actions = []
    commenter_nums = set()
    comments_only = []  # top-level comments in order (for to_index 계산)
    last_action = None  # 직전에 만들어진 action (continuation line append 대상)

    for raw_line in comments_part.split('\n'):
        line = raw_line.strip()

        if not line:
            # 빈 줄: 현재 action 안의 단락 구분자로 \n 추가 (첫 줄/마커 사이는 무시)
            if last_action is not None:
                last_action['text'] = last_action['text'].rstrip() + '\n'
            continue

        m = COMMENT_RE.match(line)
        if m:
            num = int(m.group(1))
            content = m.group(2).strip()
            commenter_nums.add(num)
            comments_only.append(num)
            last_action = {
                "action": "comment",
                "commenter_num": num,
                "text": content,
            }
            actions.append(last_action)
            continue

        m = AUTHOR_REPLY_RE.match(line)
        if m:
            content = m.group(1).strip()
            if not comments_only:
                raise ValueError(f"ㄴ 작성자 답글이 어떤 댓글에 대한 것인지 불명: {line[:40]}")
            last_action = {
                "action": "reply",
                "is_main": True,
                "to_index": len(comments_only) - 1,
                "text": content,
            }
            actions.append(last_action)
            continue

        m = COMMENTER_REPLY_RE.match(line)
        if m:
            num = int(m.group(1))
            content = m.group(2).strip()
            commenter_nums.add(num)
            if not comments_only:
                raise ValueError(f"ㄴ 댓글{num} 답글이 어떤 댓글에 대한 것인지 불명: {line[:40]}")
            last_action = {
                "action": "reply",
                "is_main": False,
                "commenter_num": num,
                "to_index": len(comments_only) - 1,
                "text": content,
            }
            actions.append(last_action)
            continue

        # 마커가 아닌 일반 줄: 직전 action 의 본문에 이어붙임 (여러 줄 댓글 지원)
        if last_action is not None:
            last_action['text'] = last_action['text'].rstrip() + '\n' + line
        # else: 최초 마커 이전의 여백/헤더 줄은 무시

    # 각 action 의 text 끝 개행 정리
    for a in actions:
        a['text'] = a['text'].strip()

    return {
        "title": title,
        "body": body,
        "actions": actions,
        "commenter_nums": sorted(commenter_nums),
        "image_nums": image_nums,
    }


def parse_scenario_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return parse_scenario_text(f.read())
