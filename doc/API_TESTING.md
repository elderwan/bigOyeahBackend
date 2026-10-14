# FitBooking API testing

## 1. Load demo data

Run `schema.sql` first, then run `sample_data.sql` against the same MySQL database.

From a MySQL client:

```powershell
mysql --host=HOST --port=27440 --user=avnadmin --password --ssl-mode=REQUIRED defaultdb < sample_data.sql
```

If the Aiven CLI connection requires a CA certificate, configure the CA options in your MySQL client according to the Aiven service instructions.

The demo password for every seeded account is:

```text
DemoPass123!
```

Seeded accounts:

| Username | Role | Purpose |
|---|---|---|
| `alex.demo` | MEMBER | Gold member, completed and confirmed bookings |
| `maya.demo` | MEMBER | Silver member, pending booking to cancel |
| `tan.coach` | COACH | Coach profile and schedule `1001` |
| `may.coach` | COACH | Second coach for discovery filters |
| `admin.demo` | ADMIN | Admin dashboard and audit log |

## 2. Start the API

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger is available at `http://localhost:8000/docs`.

## 3. Test public endpoints

```powershell
curl.exe http://localhost:8000/api/v1/courses
curl.exe "http://localhost:8000/api/v1/gyms?district=NIMMAN"
curl.exe "http://localhost:8000/api/v1/coaches?search=Tan"
curl.exe http://localhost:8000/api/v1/coaches/1/profile
curl.exe "http://localhost:8000/api/v1/coaches/1/schedule/slots?start_at=2026-10-13T09:00:00&end_at=2026-10-13T11:00:00"
```

Use the actual `coach_id` returned by the coach list if it is not `1`.

## 4. Login and call member endpoints

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/auth/login `
  -ContentType "application/json" `
  -Body '{"username":"alex.demo","password":"DemoPass123!"}'

$headers = @{ Authorization = "Bearer $($login.access_token)" }

Invoke-RestMethod -Headers $headers http://localhost:8000/api/v1/auth/me
Invoke-RestMethod -Headers $headers http://localhost:8000/api/v1/members/me
Invoke-RestMethod -Headers $headers http://localhost:8000/api/v1/members/me/dashboard
Invoke-RestMethod -Headers $headers http://localhost:8000/api/v1/members/me/bookings
Invoke-RestMethod -Headers $headers http://localhost:8000/api/v1/members/me/packages
Invoke-RestMethod -Headers $headers http://localhost:8000/api/v1/members/me/reviews
Invoke-RestMethod -Headers $headers http://localhost:8000/api/v1/members/me/progress
Invoke-RestMethod -Headers $headers http://localhost:8000/api/v1/members/me/payment-history
```

## 5. Test a member profile update

```powershell
Invoke-RestMethod `
  -Method Patch `
  -Uri http://localhost:8000/api/v1/members/me `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"fitness_goal":"Build strength and train four times each week","weight_kg":67.5}'
```

## 6. Test cancellation with the second member

```powershell
$mayaLogin = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/auth/login `
  -ContentType "application/json" `
  -Body '{"username":"maya.demo","password":"DemoPass123!"}'

$mayaHeaders = @{ Authorization = "Bearer $($mayaLogin.access_token)" }
Invoke-RestMethod -Headers $mayaHeaders http://localhost:8000/api/v1/members/me/bookings

# Replace 3 with the pending booking_id returned above.
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/members/me/bookings/3/cancel `
  -Headers $mayaHeaders `
  -ContentType "application/json" `
  -Body '{"reason":"Demo cancellation test"}'
```

## 7. Test review submission

The seeded completed booking is eligible for a review. Replace `1` with the returned
completed `booking_id` if needed:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/members/me/reviews `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"booking_id":1,"rating_professional":5,"rating_communication":5,"rating_punctuality":4,"rating_effectiveness":5,"comment":"Great demo session."}'
```

The seed already inserts a review for the completed booking, so submitting another
review for the same booking should return `409`.

## 8. Test package checkout

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/members/me/packages/purchase `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"package_type":"5+1","payment_method":"PROMPTPAY"}'
```

This creates a `member_package` row and an unpaid `orders` row. Payment-provider
confirmation is not implemented yet.

## 9. Test admin endpoints

```powershell
$adminLogin = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/auth/login `
  -ContentType "application/json" `
  -Body '{"username":"admin.demo","password":"DemoPass123!"}'

$adminHeaders = @{ Authorization = "Bearer $($adminLogin.access_token)" }
Invoke-RestMethod -Headers $adminHeaders http://localhost:8000/api/v1/admin/dashboard
Invoke-RestMethod -Headers $adminHeaders http://localhost:8000/api/v1/admin/audit-log
```
