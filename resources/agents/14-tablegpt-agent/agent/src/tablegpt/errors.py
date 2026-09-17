from langchain_core.exceptions import OutputParserException


class NoAttachmentsError(KeyError):
    def __init__(self):
        super().__init__("No file attached")


class InvalidURIError(ValueError): ...


class InvalidFileURIError(InvalidURIError):
    def __init__(self, uri: str):
        super().__init__(f"URI does not start with 'file:': {uri!r}")


class NonAbsoluteURIError(InvalidURIError):
    def __init__(self, uri: str):
        super().__init__(f"URI is not absolute: {uri!r}")


class UnsupportedFileFormatError(ValueError):
    def __init__(self, ext: str):
        super().__init__(
            f"TableGPT 目前支持 csv、tsv 以及 xlsx 文件，您上传的文件格式 {ext} 暂不支持。"  # noqa: RUF001
        )


class UnsupportedEncodingError(ValueError):
    def __init__(self, encoding: str):
        super().__init__(
            f"不支持的文件编码{encoding}，请转换成 utf-8 后重试"  # noqa: RUF001
        )


class EncodingDetectionError(LookupError):
    def __init__(self, path: str):
        super().__init__(f"Could not detect encoding for {path}")


class SimpleOutputParserException(OutputParserException):
    def __init__(self, input_text: str):
        super().__init__(f"Could not parse output: {input_text}")
