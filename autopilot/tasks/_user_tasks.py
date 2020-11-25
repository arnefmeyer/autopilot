
from autopilot import prefs
from autopilot.tasks.task import Task

import os.path as op


def load_user_tasks():

    task_file = op.join(prefs.BASEDIR, 'user_tasks.py')

    task_list = {}
    if op.exists(task_file):
        print("Loading user tasks from file", task_file)

        # load task list from python script
        from importlib.machinery import SourceFileLoader
        mod = SourceFileLoader('', task_file).load_module()
        user_tasks = mod.task_list

        # check if entries are subclasses of Task
        for name, cls in user_tasks.items():
            if issubclass(cls, Task):
                print("  found user task: {} {}".format(name, cls))
                task_list[name] = cls
            else:
                print("  not a subclass of autopilot.tasks.task.Task: {} {}".format(name, cls))
    else:
        print("Creating file for user tasks", task_file)
        with open(task_file, 'w') as f:
            lines = ['# add user tasks',
                     '#',
                     '# example:',
                     '#',
                     '# from mypackage import mytask',
                     '# task_list["mytask"] = mytask',
                     '',
                     'task_list = {}',
                     '']
            f.writelines('\n'.join(lines))

    return task_list
