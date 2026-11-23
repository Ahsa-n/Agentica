# SOP: Handling a Full Disk

## Overview
This procedure addresses how to respond when a server disk partition reaches critical capacity (>90%).

## Alert Thresholds
- Warning: 80% disk usage
- Critical: 90% disk usage
- Emergency: 95%+ disk usage

## Procedure

### Step 1: Identify the full partition
1. Run `get_disk_usage` to see all partitions
2. Identify which partition is critically full
3. Run `get_logs` to check if any services are logging errors due to disk space

### Step 2: Quick relief — clear temporary files
1. Check `/tmp` or `C:\Windows\Temp` for large temporary files
2. Clear application log archives older than 30 days
3. Remove old package cache (e.g., `apt-get clean` on Linux)

### Step 3: Identify large consumers
1. Check application log directory sizes
2. Look for database transaction logs that may need archiving
3. Check for core dump files

### Step 4: Long-term resolution
1. Archive old log files to network storage
2. Implement log rotation policy
3. Consider disk expansion request to IT infrastructure team
4. Document actions taken in the incident log

### Escalation
If disk cannot be cleared below 85% within 30 minutes, escalate to infrastructure team immediately.
