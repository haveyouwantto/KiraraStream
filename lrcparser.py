class LrcParser:
    def __init__(self, file_path, encoding='utf-8'):
        self.file_path = file_path
        self.lrc = {
            'meta':{},
            "lyrics":[]
        }
        self.current_lyric = None
        self.buffer = ""
        self.in_tag = False
        self.encoding = encoding

    def parse_char(self, char):
        if char == "[":
            self.in_tag = True
            self.parse_tag(self.buffer)
            self.buffer = ""
        elif char == "]":
            self.in_tag = False
        self.buffer += char

    def parse_tag(self, tag):
        parts = tag.split("]")
        if len(parts) == 2:
            data = parts[0][1:]
            if data[0].isalpha():
                datatag = data.split(':')
                self.lrc['meta'][datatag[0]] = datatag[1]
            else:
                text = parts[1]
                self.add_lyric(self.convert_to_seconds(data), text)
            
    def convert_to_seconds(self, timestamp):
        parts = timestamp.split(":")
        minutes = int(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds

    def add_lyric(self, timestamp, text):
        self.lrc['lyrics'].append({'time':timestamp,'text':text})

    def finalize(self):
        if self.current_lyric:
            self.lyrics.append(self.current_lyric)
        self.current_lyric = None

    def parse(self):
        with open(self.file_path, "r", encoding=self.encoding) as file:
            while True:
                char = file.read(1)
                if not char:
                    break
                self.parse_char(char)

        self.finalize()
        return self.lrc