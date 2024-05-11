import copy
import logging
import aiofiles
from aiohttp import ClientSession
from pathlib import Path
from threading import Event


MEGABYTE = 1048576


class Basicdown:
    """Base downloader class."""

    def __init__(self, interrupt: Event):
        self.curr = 0  # Downloaded size in bytes (current size)
        self.completed = False
        self.id = 0
        self.interrupt = interrupt
        self.downloaded = 0

    async def download(
        self, url: str, path: str, mode: str, session: ClientSession, **kwargs
    ) -> None:
        """Download data in chunks."""
        try:
            async with session.get(url, **kwargs) as response:
                async with aiofiles.open(path, mode) as file:
                    async for chunk in response.content.iter_chunked(MEGABYTE):
                        await file.write(chunk)
                        self.curr += len(chunk)
                        self.downloaded += len(chunk)
                        if self.interrupt.is_set():
                            break

        except Exception as e:
            self.interrupt.set()
            logging.error("(Thread: %d) [%s: %s]", self.id, type(e).__name__, e)


class Simpledown(Basicdown):
    """Class for downloading the whole file in a single segment."""

    async def worker(self, url, file_path, session, **kwargs) -> None:
        await self.download(url, file_path, "wb", session, **kwargs)
        self.completed = True


class Multidown(Basicdown):
    """Class for downloading a specific segment of the file."""

    def __init__(
        self,
        segment_id: int,
        interrupt: Event,
        **kwargs,
    ):
        super().__init__(interrupt)
        self.id = segment_id
        self.kwargs = kwargs

    async def worker(self, segement_table, session) -> None:
        url = segement_table["url"]
        overwrite = segement_table["overwrite"]
        segment_path = Path(segement_table[self.id]["segment_path"])
        start = segement_table[self.id]["start"]
        end = segement_table[self.id]["end"]
        size = segement_table[self.id]["segment_size"]

        if segment_path.exists():
            downloaded_size = segment_path.stat().st_size
            if overwrite or downloaded_size > size:
                segment_path.unlink()
            else:
                self.curr = downloaded_size

        if self.curr < size:
            start = start + self.curr
            kwargs = copy.deepcopy(self.kwargs)  # since used by others
            kwargs.setdefault("headers", {}).update({"range": f"bytes={start}-{end}"})
            await self.download(url, segment_path, "ab", session, **kwargs)

        if self.curr == size:
            self.completed = True
