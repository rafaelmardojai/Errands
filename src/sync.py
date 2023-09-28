from gi.repository import Adw
from caldav import Calendar, DAVClient, Todo
from .utils import GSettings, Log, TaskUtils, UserData, threaded

# from nextcloud_tasks_api import (
#     NextcloudTasksApi,
#     TaskFile,
#     TaskList,
#     get_nextcloud_tasks_api,
# )
# from nextcloud_tasks_api.ical import Task


class Sync:
    providers: list = []
    window: Adw.ApplicationWindow = None

    @classmethod
    def init(self, window: Adw.ApplicationWindow) -> None:
        self.window = window
        self.providers.append(SyncProviderNextcloud())
        # self.providers.append(SyncProviderTodoist())

    # @threaded
    @classmethod
    def sync(self) -> None:
        if not self.window.can_sync:
            return
        for provider in self.providers:
            if provider.can_sync:
                provider.sync()

    def _setup_providers(self) -> None:
        pass


class SyncProviderNextcloud:
    can_sync: bool = False
    calendar: Calendar = None

    def __init__(self):
        if not GSettings.get("nc-enabled"):
            Log.debug("Nextcloud sync disabled")
            return

        self.url = GSettings.get("nc-url")
        self.username = GSettings.get("nc-username")
        self.password = GSettings.get("nc-password")

        if self.url == "" or self.username == "" or self.password == "":
            Log.error("Not all Nextcloud credentials provided")
            return

        self.url = f"{self.url}/remote.php/dav/"

        with DAVClient(
            url=self.url, username=self.username, password=self.password
        ) as client:
            try:
                principal = client.principal()
                Log.debug(f"Connected to Nextcloud DAV server at '{self.url}'")
                self.can_sync = True
            except:
                Log.error(f"Can't connect to Nextcloud DAV server at '{self.url}'")
                self.can_sync = False
                return

            calendars = principal.calendars()
            errands_cal_exists: bool = False
            for cal in calendars:
                if cal.name == "Errands":
                    self.calendar = cal
                    errands_cal_exists = True
            if not errands_cal_exists:
                Log.debug("Create new calendar 'Errands' on Nextcloud")
                self.calendar = principal.make_calendar(
                    "Errands", supported_calendar_component_set=["VTODO"]
                )

    def get_tasks(self):
        todos = self.calendar.todos(include_completed=True)
        tasks: list[dict] = []
        for todo in todos:
            data: dict = {
                "id": str(todo.icalendar_component.get("uid", "")),
                "parent": str(todo.icalendar_component.get("related-to", "")),
                "text": str(todo.icalendar_component.get("summary", "")),
                "completed": True
                if str(todo.icalendar_component.get("status", False)) == "COMPLETED"
                else False,
                "color": str(todo.icalendar_component.get("x-errands-color", "")),
            }
            tasks.append(data)

        return tasks

    def sync(self):
        Log.info("Sync tasks with Nextcloud")

        data: dict = UserData.get()
        nc_ids: list[str] = [task["id"] for task in self.get_tasks()]
        to_delete: list[dict] = []

        for task in data["tasks"]:
            # Create new task on NC that was created offline
            if task["id"] not in nc_ids and not task["synced_nc"]:
                Log.debug(f"Create new task on Nextcloud: {task['id']}")
                new_todo = self.calendar.save_todo(
                    uid=task["id"],
                    summary=task["text"],
                    related_to=task["parent"],
                    x_errands_color=task["color"],
                )
                if task["completed"]:
                    new_todo.complete()
                task["synced_nc"] = True

            # Update task that was changed locally
            elif task["id"] in nc_ids and not task["synced_nc"]:
                Log.debug(f"Update task on Nextcloud: {task['id']}")
                todo = self.calendar.todo_by_uid(task["id"])
                todo.uncomplete()
                todo.icalendar_component["summary"] = task["text"]
                todo.icalendar_component["related-to"] = task["parent"]
                todo.icalendar_component["x-errands-color"] = task["color"]
                todo.save()
                if task["completed"]:
                    todo.complete()
                task["synced_nc"] = True

            # Update task that was changed on NC
            elif task["id"] in nc_ids and task["synced_nc"]:
                for nc_task in self.get_tasks():
                    if nc_task["id"] == task["id"]:
                        task["text"] = nc_task["text"]
                        task["parent"] = nc_task["parent"]
                        task["completed"] = nc_task["completed"]
                        task["color"] = nc_task["color"]
                        break

            # Delete local task that was deleted on NC
            elif task["id"] not in nc_ids and task["synced_nc"]:
                to_delete.append(task)

        # Remove deleted on NC tasks from data
        for task in to_delete:
            data["tasks"].remove(task)

        # Delete tasks on NC if they were deleted locally
        for task_id in data["deleted"]:
            try:
                Log.debug(f"Delete task from Nextcloud: {task_id}")
                todo = self.calendar.todo_by_uid(task_id)
                todo.delete()
            except:
                pass

        # Create new local task that was created on NC
        l_ids: list = [t["id"] for t in data["tasks"]]
        for task in self.get_tasks():
            if task["id"] not in l_ids:
                Log.debug(f"Copy new task from Nextcloud: {task['id']}")
                new_task: dict = TaskUtils.new_task(
                    task["text"],
                    task["id"],
                    task["parent"],
                    task["completed"],
                    False,
                    task["color"],
                    True,
                    False,
                )
                data["tasks"].append(new_task)

        UserData.set(data)


class SyncProviderTodoist:
    token: str

    def __init__(self) -> None:
        pass

    def connect(self) -> None:
        pass

    def sync(self) -> None:
        pass
