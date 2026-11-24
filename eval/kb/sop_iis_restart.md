# SOP: IIS (Internet Information Services) Restart — Windows

## Overview
Procedure for restarting IIS on Windows servers.

## Prerequisites
- WinRM connection established to target Windows server
- Administrator credentials configured in Agentica keyring

## Procedure

### Step 1: Check current status
1. Run `get_service_status W3SVC` to check IIS service status
2. Review Windows event log: `get_logs eventlog:System`
3. Check if the application pool is running

### Step 2: Notify users
1. Post maintenance notification if users are actively using the application
2. IIS restart typically takes 10-30 seconds

### Step 3: Perform the restart
1. Request restart: `restart_service W3SVC` on the Windows target
2. **This requires administrator confirmation**
3. The service restart command will be validated by the policy engine

### Step 4: Verify
1. Check service status: `get_service_status W3SVC`
2. Test port 80 or 443: `check_port <server> 80`
3. Review event log for any startup errors: `get_logs eventlog:Application`

### Application Pool Issues
If IIS service is running but application pool is stopped:
1. This requires manual intervention via IIS Manager
2. Document the issue and escalate to Windows Server team

### Common Error Codes
- Event ID 1000: Application Error — check application event log
- Event ID 7031: Service terminated unexpectedly
- HTTP 503: Service Unavailable — usually application pool stopped
