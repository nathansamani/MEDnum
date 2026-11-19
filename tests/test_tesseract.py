from mednum import tesseract

TSV = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
       "1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t\n"
       "5\t1\t1\t1\t1\t1\t10\t20\t30\t12\t95\tBonjour\n"
       "5\t1\t1\t1\t1\t2\t50\t21\t40\t12\t90\tmonde\n"
       "5\t1\t1\t1\t2\t1\t10\t50\t30\t12\t90\tsuite\n")


def test_parse_and_lines():
    words = tesseract.parse_tsv(TSV)
    assert [w["text"] for w in words] == ["Bonjour", "monde", "suite"]
    lines = tesseract.lines_of(words)
    assert len(lines) == 2 and lines[0]["x1"] == 90


def test_cache():
    calls = []
    cache = tesseract.Cache(reader=lambda image: calls.append(image) or [])
    cache("a.png"); cache("a.png")
    assert calls == ["a.png"]
