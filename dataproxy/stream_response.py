# -*- coding: utf-8 -*-

import requests
from io import BytesIO, SEEK_SET, SEEK_END

class ResponseStream(object):
    def __init__(self, request_iterator):
        self._bytes = BytesIO()
        self._iterator = request_iterator

    def _load_all(self):
        self._bytes.seek(0, SEEK_END)
        for chunk in self._iterator:
            self._bytes.write(chunk)

    def _load_until(self, goal_position):
        current_position = self._bytes.seek(0, SEEK_END)
        while current_position < goal_position:
            try:
                current_position = self._bytes.write(next(self._iterator))
            except StopIteration:
                break

    def tell(self):
        return self._bytes.tell()

    def read(self, size=None):
        left_off_at = self._bytes.tell()
        if size is None:
            self._load_all()
        else:
            goal_position = left_off_at + size
            self._load_until(goal_position)

        self._bytes.seek(left_off_at)
        return self._bytes.read(size)
    
    def seek(self, position, whence=SEEK_SET):
        if whence == SEEK_END:
            self._load_all()
        else:
            self._bytes.seek(position, whence)

def main():
    # Use the class by providing a requests stream iterator.
    response = requests.get('http://example.com/', stream=True)
    # Chunk size of 64 bytes, in this case. Adapt to your use case.
    stream = ResponseStream(response.iter_content(64))

    # Now we can read the first 100 bytes (for example) of the file
    # without loading the rest of it. Of course, it's more useful when
    # loading large files, like music images, or video. 😉
    # Seek and tell will also work as expected; important for some applications.
    stream.read(100)

if __name__ == '__main__':
    main()
