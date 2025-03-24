import simple_inotify   # type: ignore
from dockerdo.config import Session
from typing import Optional


class InotifyListener:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.inotify: Optional[simple_inotify.SimpleINotify] = None

    def register_listeners(self) -> None:
        """
        Register listeners recursively for the session's container mount point.
        """
        self.inotify = simple_inotify.SimpleINotify()
        for path in self.session.sshfs_container_mount_point.rglob("*"):
            if path.is_dir():
                self.inotify.add(path, mask=simple_inotify.IN_CLOSE_WRITE)

    def listen(self) -> None:
        if self.inotify is None:
            raise RuntimeError("Listeners not registered")
        for event in self.inotify.event_gen(yield_nones=False):
            self.session = Session.load(self.session.session_dir)
            self.session.record_modified_file(event[3].name)
            self.session.save()
