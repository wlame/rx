"""Tests for ripgrep JSON event parsing"""

from rx.rg_json import (
    parse_rg_json_event,
    RgMatchEvent,
    RgContextEvent,
    RgBeginEvent,
    RgEndEvent,
    RgSummaryEvent,
)


def test_parse_match_event():
    """Test parsing a match event from ripgrep JSON output"""
    json_line = '{"type":"match","data":{"path":{"text":"test.txt"},"lines":{"text":"error message\\n"},"line_number":42,"absolute_offset":1000,"submatches":[{"match":{"text":"error"},"start":0,"end":5}]}}'

    event = parse_rg_json_event(json_line)

    assert isinstance(event, RgMatchEvent)
    assert event.type == "match"
    assert event.data.path.text == "test.txt"
    assert event.data.line_number == 42
    assert event.data.absolute_offset == 1000
    assert event.data.lines.text == "error message\n"
    assert len(event.data.submatches) == 1
    assert event.data.submatches[0].text == "error"
    assert event.data.submatches[0].start == 0
    assert event.data.submatches[0].end == 5


def test_parse_context_event():
    """Test parsing a context event from ripgrep JSON output"""
    json_line = '{"type":"context","data":{"path":{"text":"test.txt"},"lines":{"text":"normal line\\n"},"line_number":41,"absolute_offset":980,"submatches":[]}}'

    event = parse_rg_json_event(json_line)

    assert isinstance(event, RgContextEvent)
    assert event.type == "context"
    assert event.data.path.text == "test.txt"
    assert event.data.line_number == 41
    assert event.data.absolute_offset == 980
    assert event.data.lines.text == "normal line\n"
    assert len(event.data.submatches) == 0


def test_parse_begin_event():
    """Test parsing a begin event"""
    json_line = '{"type":"begin","data":{"path":{"text":"test.txt"}}}'

    event = parse_rg_json_event(json_line)

    assert isinstance(event, RgBeginEvent)
    assert event.type == "begin"
    assert event.data.path.text == "test.txt"


def test_parse_end_event():
    """Test parsing an end event with statistics"""
    json_line = '{"type":"end","data":{"path":{"text":"test.txt"},"binary_offset":null,"stats":{"elapsed":{"secs":0,"nanos":123456,"human":"0.000123s"},"searches":1,"searches_with_match":1,"bytes_searched":1000,"bytes_printed":500,"matched_lines":5,"matches":10}}}'

    event = parse_rg_json_event(json_line)

    assert isinstance(event, RgEndEvent)
    assert event.type == "end"
    assert event.data.path.text == "test.txt"
    assert event.data.stats.matches == 10
    assert event.data.stats.matched_lines == 5


def test_parse_summary_event():
    """Test parsing a summary event"""
    json_line = '{"type":"summary","data":{"elapsed_total":{"secs":0,"nanos":500000,"human":"0.0005s"},"stats":{"elapsed":{"secs":0,"nanos":400000,"human":"0.0004s"},"searches":2,"searches_with_match":1,"bytes_searched":2000,"bytes_printed":1000,"matched_lines":10,"matches":20}}}'

    event = parse_rg_json_event(json_line)

    assert isinstance(event, RgSummaryEvent)
    assert event.type == "summary"
    assert event.data.stats.matches == 20
    assert event.data.stats.searches == 2


def test_parse_invalid_json():
    """Test parsing invalid JSON returns None"""
    event = parse_rg_json_event("not valid json")
    assert event is None


def test_parse_empty_line():
    """Test parsing empty line returns None"""
    event = parse_rg_json_event("")
    assert event is None


def test_parse_bytes_input():
    """Test parsing bytes input"""
    json_line = b'{"type":"match","data":{"path":{"text":"test.txt"},"lines":{"text":"test\\n"},"line_number":1,"absolute_offset":0,"submatches":[]}}'

    event = parse_rg_json_event(json_line)

    assert isinstance(event, RgMatchEvent)
    assert event.data.line_number == 1


def test_submatch_text_property():
    """Test the text property of RgSubmatch"""
    json_line = '{"type":"match","data":{"path":{"text":"test.txt"},"lines":{"text":"error\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"error"},"start":0,"end":5}]}}'

    event = parse_rg_json_event(json_line)

    assert isinstance(event, RgMatchEvent)
    submatch = event.data.submatches[0]
    assert submatch.text == "error"


def test_get_match_absolute_offsets():
    """Test calculating absolute offsets for submatches"""
    json_line = '{"type":"match","data":{"path":{"text":"test.txt"},"lines":{"text":"error warning\\n"},"line_number":1,"absolute_offset":100,"submatches":[{"match":{"text":"error"},"start":0,"end":5},{"match":{"text":"warning"},"start":6,"end":13}]}}'

    event = parse_rg_json_event(json_line)

    assert isinstance(event, RgMatchEvent)
    offsets = event.data.get_match_absolute_offsets()
    assert offsets == [100, 106]  # 100 + 0, 100 + 6
