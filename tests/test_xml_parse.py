"""XML tool_call format parsing tests"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'frok'))
from tools import parse_tool_calls

KNOWN = {"write_file", "read_file", "finish", "execute_command", "list_directory"}


def test_xml_no_params():
    # Build XML tags dynamically to avoid system interference
    tc = "<" + "tool_call" + ">\n<" + "function" + ">list_directory</" + "function" + ">\n</" + "tool_call" + ">"
    calls = parse_tool_calls(tc, KNOWN)
    assert len(calls) == 1
    assert calls[0]["name"] == "list_directory"


def test_xml_with_params():
    tc = ("<" + "tool_call" + ">\n<" + "function" + ">execute_command</" + "function" + ">\n"
          "<command>dir test</command>\n"
          "</" + "tool_call" + ">")
    calls = parse_tool_calls(tc, KNOWN)
    assert len(calls) == 1
    assert calls[0]["name"] == "execute_command"
    assert calls[0]["parameters"]["command"] == "dir test"


def test_xml_unknown_filtered():
    tc = "<" + "tool_call" + ">\n<" + "function" + ">unknown_tool</" + "function" + ">\n</" + "tool_call" + ">"
    calls = parse_tool_calls(tc, KNOWN)
    assert len(calls) == 0


def test_xml_no_filter():
    tc = "<" + "tool_call" + ">\n<" + "function" + ">any_tool</" + "function" + ">\n</" + "tool_call" + ">"
    calls = parse_tool_calls(tc, None)
    assert len(calls) == 1


def test_json_still_works():
    text = '```tool_call\n{"name": "write_file", "parameters": {"path": "a.py", "content": "x"}}\n```'
    calls = parse_tool_calls(text, KNOWN)
    assert len(calls) == 1
    assert calls[0]["name"] == "write_file"


def test_bare_json_still_works():
    text = '{"name": "finish", "parameters": {"result": "done"}}'
    calls = parse_tool_calls(text, KNOWN)
    assert len(calls) == 1
    assert calls[0]["name"] == "finish"
