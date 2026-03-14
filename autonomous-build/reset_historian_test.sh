#!/bin/bash
# Reset state to test the historian on TASK-002c
# Run from autonomous-build/ directory

set -e

cd /workspaces/cisTEMx

# 1. Point start tag at commit before first TASK-002 work
git tag -f autobuild/TASK-002c/start 048ef5ac59b5fd6a6cfb361a5d47c07510fe0ed2

# 2. Remove verified tag if it exists
git tag -d autobuild/TASK-002c/verified 2>/dev/null || true

# 3. Reset TASK-002c to in_progress with oracle checkpoint
cd autonomous-build
python3 -c "
from orchestrator import TaskManager
tm = TaskManager()
for t in tm.prd['tasks']:
    if t['id'] == 'TASK-002c':
        t['status'] = 'in_progress'
        t.pop('completed_at', None)
tm.set_checkpoint('TASK-002c', 'oracle', 2, '048ef5ac59b5fd6a6cfb361a5d47c07510fe0ed2')
tm.save()
print('TASK-002c reset: in_progress, checkpoint=oracle')
"

echo ""
echo "State reset. Run with:"
echo "  HISTORIAN_DEBUG_EXIT=1 python orchestrator.py --phase 0 --stream --max-iterations 500 --resume"
