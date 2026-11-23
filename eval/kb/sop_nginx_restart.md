# SOP: Nginx Service Restart

## Overview
Procedure for safely restarting the Nginx web server.

## When to Use
- Nginx is not responding to web requests
- Configuration changes need to be applied
- Service health check shows Nginx as DOWN or DEGRADED

## Pre-restart Checklist
1. Verify there is no active maintenance window conflict
2. Check active connections with `get_network_stats`
3. Notify stakeholders if traffic will be briefly interrupted (usually < 5 seconds)

## Procedure

### Step 1: Check current status
1. Run `get_service_status nginx`
2. Run `get_logs` with source `journal:nginx` to understand why it's not running
3. Check port 80 and 443 with `check_port`

### Step 2: Test configuration before restart
1. On Linux: `nginx -t` validates configuration without restarting
2. If configuration test fails, do NOT proceed with restart until config is fixed

### Step 3: Perform the restart
1. Request restart: `restart_service nginx`
2. **This requires administrator confirmation**
3. The restart typically completes in 2-5 seconds

### Step 4: Verify
1. Run `get_service_status nginx` — should show "active"
2. Check port 80: `check_port localhost 80`
3. Check port 443: `check_port localhost 443`
4. Verify web application responds (HTTP check)

### Emergency: If nginx fails to start
1. Check logs: `get_logs journal:nginx`
2. Common issues:
   - Port 80/443 already in use by another process
   - SSL certificate expired or missing
   - Configuration syntax error
3. Escalate to web infrastructure team if unresolved after 15 minutes
