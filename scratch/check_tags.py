from html.parser import HTMLParser

class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if not self.stack:
            self.errors.append(f"Unexpected closing tag </{tag}> at line {self.getpos()[0]}")
            return
        
        # Find matching start tag in stack
        found = False
        for idx in range(len(self.stack)-1, -1, -1):
            if self.stack[idx][0] == tag:
                # Remove everything from stack above this match (auto-closing tags)
                self.stack = self.stack[:idx]
                found = True
                break
        if not found:
            self.errors.append(f"Mismatched closing tag </{tag}> at line {self.getpos()[0]}")

with open('templates/employees/profile.html', 'r', encoding='utf-8') as f:
    html = f.read()

parser = MyHTMLParser()
parser.feed(html)
for err in parser.errors:
    print(err)
print("Stack remaining:", parser.stack)
