# SOP: Handling a Stopped Service

## Overview
This procedure describes how to diagnose and recover a stopped system service.

## Prerequisites
- Administrative or sudo access to the target server
- Access to the Agentica management console

## Procedure

### Step 1: Identify the stopped service
1. Run `get_service_status <service_name>` to confirm the service is stopped
2. Run `get_logs` with source `journal:<service_name>` to review recent log entries
3. Note the last error message and timestamp

### Step 2: Diagnose the cause
1. Check if the service binary exists
2. Review configuration files for syntax errors
3. Check for port conflicts using `check_port`
4. Check disk space with `get_disk_usage` — services often fail when disk is full

### Step 3: Restart the service
1. Request a restart: `restart_service <service_name>`
2. This action requires administrator confirmation
3. Wait for the restart confirmation

### Step 4: Verify the service is running
1. Run `get_service_status <service_name>` again
2. Check port availability with `check_port`
3. Review logs for startup errors: `get_logs journal:<service_name>`

### Step 5: Escalate if needed
If the service fails to start after restart:
1. Document the error messages
2. Escalate to Level 2 support
3. Consider restoring from last known good configuration
