from deepagents.backends.utils import slice_read_response, grep_matches_from_files
import json
checks=[]
for separator in ["\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]:
    content="def alpha():\n    return 1\n\n"+separator+"\ndef beta():\n    SECRET_TARGET = 1\n    return 2\n"
    data={"content":content,"modified_at":"2024-01-01T00:00:00Z"}
    grep=grep_matches_from_files({"/mod.py":data},"SECRET_TARGET","/")
    read=slice_read_response(data,5,1)
    checks.append({"separator":repr(separator),"grep":grep.matches,"read":read.file_data["content"],"total_lines":read.total_lines,"pass":read.file_data["content"]=="    SECRET_TARGET = 1\n" and read.total_lines==7})
for content,expected in [("a\nb\n","a\nb\n"),("a\r\nb","a\nb"),("a\rb","a\nb"),("a","a")]:
    read=slice_read_response({"content":content},0,99)
    checks.append({"input":repr(content),"pass":read.file_data["content"]==expected})
print(json.dumps(checks,ensure_ascii=True))
raise SystemExit(0 if all(c["pass"] for c in checks) else 1)
