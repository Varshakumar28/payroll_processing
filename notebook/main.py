# main.py
from fastapi import FastAPI, Depends, HTTPException, status, Security, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from jose import jwt, JWTError
import hashlib
from datetime import datetime
import pyodbc
from fastapi.middleware.cors import CORSMiddleware
from weasyprint import HTML, CSS

app = FastAPI(
    title="Timesheet & Payroll API",
    version="1.0",
    description="Employees self-register, submit timesheets, view payroll."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- JWT config ---
SECRET_KEY = "your‑very‑strong‑secret"  # rotate in prod!
ALGORITHM = "HS256"

# --- HTTP Bearer scheme ---
bearer_scheme = HTTPBearer(bearerFormat="JWT")

# --- DB dependency ---


def get_db():
    conn = pyodbc.connect(
        r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
        r"DBQ=./database.accdb;"
    )
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    finally:
        conn.close()

# --- Utility: password hashing ---


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# --- Pydantic models ---


class EmployeeCreate(BaseModel):
    first_name: str = Field(..., example="Alice")
    last_name:  str = Field(..., example="Smith")
    email:      EmailStr
    phone:      str = Field(..., example="+91-9876543210")
    department: str = Field(..., example="Engineering")
    password:   str = Field(..., min_length=6, example="secretpass")


class EmployeeLogin(BaseModel):
    email:    EmailStr
    password: str = Field(..., example="secretpass")


class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"


class TokenData(BaseModel):
    employee_id: int
    first_name:  str
    last_name:   str
    email:       EmailStr
    phone:       str
    department:  str
    role:        int


class TimesheetCreate(BaseModel):
    date_worked:      str = Field(..., example="2025-04-21")
    hours_worked:     float = Field(..., example=8.0)
    overtime_hours:   float = Field(0.0,   example=2.0)
    work_description: str = Field(..., example="Feature development")


class TimesheetOut(BaseModel):
    timesheet_id:     int
    date_worked:      str
    hours_worked:     float
    overtime_hours:   float
    work_description: str
    submission_status: str
    manager_comments: Optional[str]


class PayrollOut(BaseModel):
    payroll_id:     int
    payroll_date:   str
    approved_hours: float
    overtime_hours: float
    gross_salary:   float
    net_pay:        float


class MetricsOut(BaseModel):
    total_timesheets:   int
    pending_timesheets: int
    approved_timesheets: int
    payroll_runs:       int

# --- Manager Pydantic models ---


class EmployeeOut(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    department: str
    role: int


class EmployeeUpdate(BaseModel):
    phone: Optional[str] = Field(None, example="+91-1234567890")
    department: Optional[str] = Field(None, example="Sales")


class ManagerTimesheetOut(BaseModel):
    timesheet_id:     int
    employee_id:      int
    date_worked:      str
    hours_worked:     float
    overtime_hours:   float
    work_description: str
    submission_status: str
    manager_comments: Optional[str]


class StatusUpdate(BaseModel):
    submission_status: str = Field(..., example="Approved")
    manager_comments:  Optional[str] = Field(None, example="Looks good")


class PayrateCreate(BaseModel):
    employee_id:    int = Field(..., example=1)
    effective_date: str = Field(..., example="2025-04-01")
    hourly_rate:    float = Field(..., example=500.0)
    overtime_rate:  float = Field(..., example=750.0)


class PayrateOut(PayrateCreate):
    payrate_id: int


class PayrollCreate(BaseModel):
    employee_id:     int = Field(..., example=1)
    payroll_date:    str = Field(..., example="2025-04-30")
    approved_hours:  float = Field(..., example=160.0)
    overtime_hours:  float = Field(..., example=10.0)
    gross_salary:    float = Field(..., example=80000.0)
    net_pay:         float = Field(..., example=70000.0)


class ManagerPayrollOut(PayrollCreate):
    payroll_id: int


# --- Pydantic models for Deductions ---

class DeductionBase(BaseModel):
    payroll_id:    int = Field(..., example=1)
    deduction_type: str = Field(..., example="Health Insurance")
    amount:        float = Field(..., example=150.00)


class DeductionCreate(DeductionBase):
    pass


class DeductionUpdate(BaseModel):
    deduction_type: Optional[str] = Field(None, example="Retirement Plan")
    amount:         Optional[float] = Field(None, example=200.00)


class DeductionOut(DeductionBase):
    deduction_id: int

# Pydantic Admin


class UserCreate(BaseModel):
    first_name: str = Field(..., example="Alice")
    last_name:  str = Field(..., example="Smith")
    email:      EmailStr = Field(..., example="alice@example.com")
    phone:      str = Field(..., example="+91-1234567890")
    department: str = Field(..., example="HR")
    password:   str = Field(..., example="s3cr3tPass!")


class UserOut(BaseModel):
    employee_id: int
    first_name:  str
    last_name:   str
    email:       EmailStr
    phone:       str
    department:  str
    role:        int


class RoleUpdate(BaseModel):
    role: int = Field(..., ge=0, le=2, example=1)


# --- Auth & RBAC dependency ---


def create_jwt(data: dict) -> str:
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def get_current_employee(
    creds: HTTPAuthorizationCredentials = Security(bearer_scheme)
) -> TokenData:
    """
    Decodes JWT from 'Authorization: Bearer <token>' header
    and returns full TokenData (incl. role).
    """
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY,
                             algorithms=[ALGORITHM])
        return TokenData(**payload)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

# --- Public endpoints ---


@app.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new employee"
)
def register(emp: EmployeeCreate, db=Depends(get_db)):
    """
    Creates a new Employee (role=0).
    """
    db.execute("SELECT 1 FROM Employee WHERE Email=?;", emp.email)
    if db.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    pw_hash = hash_password(emp.password)
    db.execute(
        """
        INSERT INTO Employee
          (FirstName, LastName, Email, PhoneNumber, Department, Password, Role)
        VALUES (?, ?, ?, ?, ?, ?, 0);
        """,
        emp.first_name, emp.last_name, emp.email,
        emp.phone, emp.department, pw_hash
    )
    db.execute("SELECT @@IDENTITY;")
    emp_id = db.fetchone()[0]
    token = create_jwt({
        "employee_id": emp_id,
        "first_name":  emp.first_name,
        "last_name":   emp.last_name,
        "email":       emp.email,
        "phone":       emp.phone,
        "department":  emp.department,
        "role":        0
    })
    return {"access_token": token}


@app.post(
    "/login",
    response_model=Token,
    summary="Employee login → returns JWT"
)
def login(creds: EmployeeLogin, db=Depends(get_db)):
    """
    Validates credentials and returns a JWT with all user fields.
    """
    db.execute(
        """
        SELECT EmployeeID, FirstName, LastName, Email, PhoneNumber,
               Department, Password, Role
          FROM Employee WHERE Email=?;
        """,
        creds.email
    )
    row = db.fetchone()
    if not row or hash_password(creds.password) != row[6]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or password"
        )
    emp_id, fn, ln, email, phone, dept, _pw, role = row
    token = create_jwt({
        "employee_id": emp_id,
        "first_name":  fn,
        "last_name":   ln,
        "email":       email,
        "phone":       phone,
        "department":  dept,
        "role":        role
    })
    return {"access_token": token}

# --- Employee‐only endpoints (use Security to inject auth into OpenAPI) ---


@app.get(
    "/me",
    response_model=TokenData,
    summary="Get current employee profile"
)
def read_profile(current: TokenData = Depends(get_current_employee)):
    """
    Returns decoded JWT payload (incl. role).
    """
    return current


@app.post(
    "/timesheets",
    response_model=TimesheetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new timesheet entry"
)
def create_timesheet(
    ts: TimesheetCreate,
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db),
):
    """
    Inserts a new timesheet (SubmissionStatus='Pending') and returns it.
    """
    db.execute(
        """
        INSERT INTO Timesheet
          (EmployeeID, DateWorked, HoursWorked, OvertimeHours, WorkDescription, SubmissionStatus)
        VALUES (?, ?, ?, ?, ?, 'Pending');
        """,
        current.employee_id,
        ts.date_worked,
        ts.hours_worked,
        ts.overtime_hours,
        ts.work_description,
    )
    db.execute("SELECT @@IDENTITY;")
    ts_id = db.fetchone()[0]

    db.execute("SELECT * FROM Timesheet WHERE TimesheetID=?;", ts_id)
    r = db.fetchone()
    dw = r[2].strftime("%Y-%m-%d") if isinstance(r[2], datetime) else str(r[2])

    return TimesheetOut(
        timesheet_id=r[0],
        date_worked=dw,
        hours_worked=r[3],
        overtime_hours=r[4],
        work_description=r[5],
        submission_status=r[6],
        manager_comments=r[7],
    )


@app.get(
    "/timesheets",
    response_model=List[TimesheetOut],
    summary="List your own timesheets"
)
def list_timesheets(
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db),
):
    """
    Returns all timesheet entries for the logged-in employee.
    """
    db.execute(
        "SELECT * FROM Timesheet WHERE EmployeeID=? ORDER BY DateWorked DESC;",
        current.employee_id,
    )
    out: List[TimesheetOut] = []
    for r in db.fetchall():
        dw = r[2].strftime("%Y-%m-%d") if isinstance(r[2],
                                                     datetime) else str(r[2])
        out.append(TimesheetOut(
            timesheet_id=r[0],
            date_worked=dw,
            hours_worked=r[3],
            overtime_hours=r[4],
            work_description=r[5],
            submission_status=r[6],
            manager_comments=r[7],
        ))
    return out


@app.put(
    "/timesheets/{ts_id}",
    response_model=TimesheetOut,
    summary="Update your pending timesheet"
)
def update_timesheet(
    ts_id: int,
    ts: TimesheetCreate,
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db),
):
    """
    Allows editing only if the entry is still 'Pending'.
    """
    db.execute(
        "SELECT EmployeeID, SubmissionStatus FROM Timesheet WHERE TimesheetID=?;",
        ts_id
    )
    row = db.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    if row[0] != current.employee_id:
        raise HTTPException(status_code=403, detail="Not your timesheet")
    if row[1] != "Pending":
        raise HTTPException(
            status_code=400, detail="Cannot edit after approval/rejection")

    db.execute(
        """
        UPDATE Timesheet SET
          DateWorked=?, HoursWorked=?, OvertimeHours=?, WorkDescription=?
        WHERE TimesheetID=?;
        """,
        ts.date_worked,
        ts.hours_worked,
        ts.overtime_hours,
        ts.work_description,
        ts_id
    )

    db.execute("SELECT * FROM Timesheet WHERE TimesheetID=?;", ts_id)
    r = db.fetchone()
    dw = r[2].strftime("%Y-%m-%d") if isinstance(r[2], datetime) else str(r[2])

    return TimesheetOut(
        timesheet_id=r[0],
        date_worked=dw,
        hours_worked=r[3],
        overtime_hours=r[4],
        work_description=r[5],
        submission_status=r[6],
        manager_comments=r[7],
    )


@app.delete(
    "/timesheets/{ts_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your pending timesheet"
)
def delete_timesheet(
    ts_id: int,
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db)
):
    """
    Can only delete if status is still 'Pending'.
    """
    db.execute(
        "SELECT EmployeeID, SubmissionStatus FROM Timesheet WHERE TimesheetID=?;",
        ts_id
    )
    row = db.fetchone()
    if not row:
        raise HTTPException(404, "Timesheet not found")
    if row[0] != current.employee_id:
        raise HTTPException(403, "Not your timesheet")
    if row[1] != "Pending":
        raise HTTPException(400, "Cannot delete after approval/rejection")

    db.execute("DELETE FROM Timesheet WHERE TimesheetID=?;", ts_id)
    return


@app.get(
    "/payrolls",
    response_model=List[PayrollOut],
    summary="View your payroll history"
)
def list_payrolls(
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db),
):
    """
    Returns all payroll runs for the logged-in employee.
    """
    db.execute(
        "SELECT * FROM Payroll WHERE EmployeeID=? ORDER BY PayrollDate DESC;",
        current.employee_id,
    )
    out: List[PayrollOut] = []
    for r in db.fetchall():
        pd = r[2].strftime("%Y-%m-%d") if isinstance(r[2],
                                                     datetime) else str(r[2])
        out.append(PayrollOut(
            payroll_id=r[0],
            payroll_date=pd,
            approved_hours=r[3],
            overtime_hours=r[4],
            gross_salary=float(r[5]),
            net_pay=float(r[6]),
        ))
    return out

# --- add this endpoint after your existing routes ---


@app.get(
    "/metrics",
    response_model=MetricsOut,
    summary="Get dashboard metrics (employee vs. manager/admin)"
)
def get_metrics(
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db)
):
    """
    If role==0, returns metrics for the logged‑in employee.
    If role>=1, returns aggregate metrics for all employees.
    """
    if current.role == 0:
        # employee‑scoped
        db.execute(
            "SELECT COUNT(*) FROM Timesheet WHERE EmployeeID=?;",
            current.employee_id
        )
        total = db.fetchone()[0]
        db.execute(
            "SELECT COUNT(*) FROM Timesheet WHERE EmployeeID=? AND SubmissionStatus='Pending';",
            current.employee_id
        )
        pending = db.fetchone()[0]
        db.execute(
            "SELECT COUNT(*) FROM Timesheet WHERE EmployeeID=? AND SubmissionStatus='Approved';",
            current.employee_id
        )
        approved = db.fetchone()[0]
        db.execute(
            "SELECT COUNT(*) FROM Payroll WHERE EmployeeID=?;",
            current.employee_id
        )
        payrolls = db.fetchone()[0]
    else:
        # manager/admin: global
        db.execute("SELECT COUNT(*) FROM Timesheet;")
        total = db.fetchone()[0]
        db.execute(
            "SELECT COUNT(*) FROM Timesheet WHERE SubmissionStatus='Pending';")
        pending = db.fetchone()[0]
        db.execute(
            "SELECT COUNT(*) FROM Timesheet WHERE SubmissionStatus='Approved';")
        approved = db.fetchone()[0]
        db.execute("SELECT COUNT(*) FROM Payroll;")
        payrolls = db.fetchone()[0]

    return MetricsOut(
        total_timesheets=total,
        pending_timesheets=pending,
        approved_timesheets=approved,
        payroll_runs=payrolls
    )

# --- Manager dependency check ---


def require_manager(current: TokenData = Depends(get_current_employee)):
    if current.role < 1:
        raise HTTPException(status_code=403, detail="Manager access required")
    return current

# --- Adimn dependency check --


def require_admin(current: TokenData = Depends(get_current_employee)):
    if current.role < 2:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current

# --- Employee management ---


@app.get(
    "/employees",
    response_model=List[EmployeeOut],
    summary="List all employees (Manager/Admin only)"
)
def list_employees(
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Returns basic info for every employee.
    """
    db.execute(
        "SELECT EmployeeID, FirstName, LastName, Email, PhoneNumber, Department, Role FROM Employee;"
    )
    rows = db.fetchall()
    return [
        EmployeeOut(
            employee_id=r[0],
            first_name=r[1],
            last_name=r[2],
            email=r[3],
            phone=r[4],
            department=r[5],
            role=r[6]
        ) for r in rows
    ]


@app.put(
    "/employees/{emp_id}",
    response_model=EmployeeOut,
    summary="Update an employee's phone or department (Manager/Admin only)"
)
def update_employee(
    emp_id: int,
    upd: EmployeeUpdate,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Updates phone and/or department for the specified employee.
    """
    # Verify exists
    db.execute("SELECT EmployeeID FROM Employee WHERE EmployeeID=?;", emp_id)
    if not db.fetchone():
        raise HTTPException(status_code=404, detail="Employee not found")

    # Build SET clause dynamically
    sets, params = [], []
    if upd.phone is not None:
        sets.append("PhoneNumber=?")
        params.append(upd.phone)
    if upd.department is not None:
        sets.append("Department=?")
        params.append(upd.department)
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    sql = f"UPDATE Employee SET {', '.join(sets)} WHERE EmployeeID=?;"
    db.execute(sql, *params, emp_id)

    # Return updated record
    db.execute(
        "SELECT EmployeeID, FirstName, LastName, Email, PhoneNumber, Department, Role "
        "FROM Employee WHERE EmployeeID=?;",
        emp_id
    )
    r = db.fetchone()
    return EmployeeOut(
        employee_id=r[0],
        first_name=r[1],
        last_name=r[2],
        email=r[3],
        phone=r[4],
        department=r[5],
        role=r[6]
    )

# --- Timesheet approval ---


@app.get(
    "/timesheets/all",
    response_model=List[ManagerTimesheetOut],
    summary="List all timesheets (Manager/Admin only)"
)
def list_all_timesheets(
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Returns every timesheet across all employees.
    """
    db.execute("SELECT * FROM Timesheet;")
    rows = db.fetchall()
    out = []
    for r in rows:
        dw = r[2].strftime("%Y-%m-%d") if hasattr(r[2],
                                                  'strftime') else str(r[2])
        out.append(ManagerTimesheetOut(
            timesheet_id=r[0],
            employee_id=r[1],
            date_worked=dw,
            hours_worked=r[3],
            overtime_hours=r[4],
            work_description=r[5],
            submission_status=r[6],
            manager_comments=r[7]
        ))
    return out


@app.put(
    "/timesheets/{ts_id}/approve",
    response_model=ManagerTimesheetOut,
    summary="Approve/reject a timesheet (Manager/Admin only)"
)
def approve_timesheet(
    ts_id: int,
    upd: StatusUpdate,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Sets SubmissionStatus & ManagerComments on a timesheet.
    """
    db.execute(
        "SELECT * FROM Timesheet WHERE TimesheetID=?;",
        ts_id
    )
    row = db.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Timesheet not found")

    # Update
    db.execute(
        """
        UPDATE Timesheet SET
          SubmissionStatus=?, ManagerComments=?
        WHERE TimesheetID=?;
        """,
        upd.submission_status,
        upd.manager_comments,
        ts_id
    )

    # Return updated
    dw = row[2].strftime("%Y-%m-%d") if hasattr(row[2],
                                                'strftime') else str(row[2])
    return ManagerTimesheetOut(
        timesheet_id=row[0],
        employee_id=row[1],
        date_worked=dw,
        hours_worked=row[3],
        overtime_hours=row[4],
        work_description=row[5],
        submission_status=upd.submission_status,
        manager_comments=upd.manager_comments
    )

# --- Payrate management ---


@app.get(
    "/payrates",
    response_model=List[PayrateOut],
    summary="List all payrates (Manager/Admin only)"
)
def list_payrates(
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Returns hourly & overtime rates for everyone.
    """
    db.execute(
        "SELECT PayrateID, EmployeeID, EffectiveDate, HourlyRate, OvertimeRate FROM Payrate;"
    )
    rows = db.fetchall()
    return [
        PayrateOut(
            payrate_id=r[0],
            employee_id=r[1],
            effective_date=r[2].strftime(
                "%Y-%m-%d") if hasattr(r[2], 'strftime') else str(r[2]),
            hourly_rate=float(r[3]),
            overtime_rate=float(r[4])
        )
        for r in rows
    ]


@app.post(
    "/payrates",
    response_model=PayrateOut,
    status_code=201,
    summary="Create a new payrate (Manager/Admin only)"
)
def create_payrate(
    pr: PayrateCreate,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Inserts a new payrate record.
    """
    db.execute(
        """
        INSERT INTO Payrate
          (EmployeeID, EffectiveDate, HourlyRate, OvertimeRate)
        VALUES (?, ?, ?, ?);
        """,
        pr.employee_id, pr.effective_date, pr.hourly_rate, pr.overtime_rate
    )
    db.execute("SELECT @@IDENTITY;")
    pr_id = db.fetchone()[0]
    return PayrateOut(**pr.dict(), payrate_id=pr_id)


@app.put(
    "/payrates/{pr_id}",
    response_model=PayrateOut,
    summary="Update a payrate (Manager/Admin only)"
)
def update_payrate(
    pr_id: int,
    pr: PayrateCreate,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Updates an existing payrate.
    """
    db.execute("SELECT 1 FROM Payrate WHERE PayrateID=?;", pr_id)
    if not db.fetchone():
        raise HTTPException(status_code=404, detail="Payrate not found")

    db.execute(
        """
        UPDATE Payrate SET
          EmployeeID=?, EffectiveDate=?, HourlyRate=?, OvertimeRate=?
        WHERE PayrateID=?;
        """,
        pr.employee_id, pr.effective_date, pr.hourly_rate, pr.overtime_rate, pr_id
    )
    return PayrateOut(**pr.dict(), payrate_id=pr_id)

# --- Payroll runs ---


@app.get(
    "/payrolls/all",
    response_model=List[ManagerPayrollOut],
    summary="List all payroll runs (Manager/Admin only)"
)
def list_all_payrolls(
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Returns every payroll record across all employees.
    """
    db.execute("SELECT * FROM Payroll;")
    rows = db.fetchall()
    out = []
    for r in rows:
        pd = r[2].strftime("%Y-%m-%d") if hasattr(r[2],
                                                  'strftime') else str(r[2])
        out.append(ManagerPayrollOut(
            payroll_id=r[0],
            employee_id=r[1],
            payroll_date=pd,
            approved_hours=r[3],
            overtime_hours=r[4],
            gross_salary=float(r[5]),
            net_pay=float(r[6])
        ))
    return out


@app.post(
    "/payrolls",
    response_model=ManagerPayrollOut,
    status_code=201,
    summary="Create a payroll run (Manager/Admin only)"
)
def create_payroll(
    pc: PayrollCreate,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Inserts a payroll record for an employee.
    """
    db.execute(
        """
        INSERT INTO Payroll
          (EmployeeID, PayrollDate, ApprovedHours, OvertimeHours, GrossSalary, NetPay)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        pc.employee_id, pc.payroll_date, pc.approved_hours,
        pc.overtime_hours,  pc.gross_salary,  pc.net_pay
    )
    db.execute("SELECT @@IDENTITY;")
    pay_id = db.fetchone()[0]
    return ManagerPayrollOut(**pc.dict(), payroll_id=pay_id)


@app.put(
    "/payrolls/{pay_id}",
    response_model=ManagerPayrollOut,
    summary="Update a payroll run (Manager/Admin only)"
)
def update_payroll(
    pay_id: int,
    pc: PayrollCreate,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Updates an existing payroll record.
    """
    db.execute("SELECT 1 FROM Payroll WHERE PayrollID=?;", pay_id)
    if not db.fetchone():
        raise HTTPException(status_code=404, detail="Payroll not found")

    db.execute(
        """
        UPDATE Payroll SET
          EmployeeID=?, PayrollDate=?, ApprovedHours=?,
          OvertimeHours=?, GrossSalary=?, NetPay=?
        WHERE PayrollID=?;
        """,
        pc.employee_id, pc.payroll_date, pc.approved_hours,
        pc.overtime_hours,  pc.gross_salary,  pc.net_pay,
        pay_id
    )
    return ManagerPayrollOut(**pc.dict(), payroll_id=pay_id)


@app.delete(
    "/payrolls/{pay_id}",
    status_code=204,
    summary="Delete a payroll run (Manager/Admin only)"
)
def delete_payroll(
    pay_id: int,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Deletes the specified payroll record.
    """
    db.execute("SELECT 1 FROM Payroll WHERE PayrollID=?;", pay_id)
    if not db.fetchone():
        raise HTTPException(status_code=404, detail="Payroll not found")

    db.execute("DELETE FROM Payroll WHERE PayrollID=?;", pay_id)
    return

# --- CRUD endpoints for Deductions ---


@app.get(
    "/deductions",
    response_model=List[DeductionOut],
    summary="List deductions (Manager/Admin only)"
)
def list_deductions(
    payroll_id: Optional[int] = None,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    List all deductions, or filter by ?payroll_id=XYZ.
    """
    if payroll_id is not None:
        db.execute(
            "SELECT DeductionID, PayrollID, DeductionType, Amount "
            "FROM Deductions WHERE PayrollID=?;",
            payroll_id
        )
    else:
        db.execute(
            "SELECT DeductionID, PayrollID, DeductionType, Amount "
            "FROM Deductions;"
        )
    rows = db.fetchall()
    return [
        DeductionOut(
            deduction_id=r[0],
            payroll_id=r[1],
            deduction_type=r[2],
            amount=float(r[3]),
        )
        for r in rows
    ]


@app.post(
    "/deductions",
    response_model=DeductionOut,
    status_code=201,
    summary="Create a deduction (Manager/Admin only)"
)
def create_deduction(
    d: DeductionCreate,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Insert a new deduction record.
    """
    db.execute(
        "INSERT INTO Deductions (PayrollID, DeductionType, Amount) VALUES (?, ?, ?);",
        d.payroll_id, d.deduction_type, d.amount
    )
    db.execute("SELECT @@IDENTITY;")
    ded_id = db.fetchone()[0]
    return DeductionOut(**d.dict(), deduction_id=ded_id)


@app.put(
    "/deductions/{ded_id}",
    response_model=DeductionOut,
    summary="Update a deduction (Manager/Admin only)"
)
def update_deduction(
    ded_id: int,
    upd: DeductionUpdate,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Update type and/or amount for an existing deduction.
    """
    # Check exists
    db.execute("SELECT 1 FROM Deductions WHERE DeductionID=?;", ded_id)
    if not db.fetchone():
        raise HTTPException(status_code=404, detail="Deduction not found")

    # Build SET clause
    sets, params = [], []
    if upd.deduction_type is not None:
        sets.append("DeductionType=?")
        params.append(upd.deduction_type)
    if upd.amount is not None:
        sets.append("Amount=?")
        params.append(upd.amount)
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    sql = f"UPDATE Deductions SET {', '.join(sets)} WHERE DeductionID=?;"
    db.execute(sql, *params, ded_id)

    # Return updated
    db.execute(
        "SELECT DeductionID, PayrollID, DeductionType, Amount "
        "FROM Deductions WHERE DeductionID=?;",
        ded_id
    )
    r = db.fetchone()
    return DeductionOut(
        deduction_id=r[0],
        payroll_id=r[1],
        deduction_type=r[2],
        amount=float(r[3]),
    )


@app.delete(
    "/deductions/{ded_id}",
    status_code=204,
    summary="Delete a deduction (Manager/Admin only)"
)
def delete_deduction(
    ded_id: int,
    mgr: TokenData = Depends(require_manager),
    db=Depends(get_db)
):
    """
    Delete the specified deduction.
    """
    db.execute("SELECT 1 FROM Deductions WHERE DeductionID=?;", ded_id)
    if not db.fetchone():
        raise HTTPException(status_code=404, detail="Deduction not found")
    db.execute("DELETE FROM Deductions WHERE DeductionID=?;", ded_id)
    return

# Admin routes


@app.post(
    "/users/manager",
    response_model=UserOut,
    status_code=201,
    summary="Create a new Manager (Admin only)"
)
def create_manager(
    u: UserCreate,
    admin: TokenData = Depends(require_admin),
    db=Depends(get_db)
):
    """
    Inserts a new Employee record with role=1 (Manager).
    """
    # check email uniqueness
    db.execute("SELECT 1 FROM Employee WHERE Email=?;", u.email)
    if db.fetchone():
        raise HTTPException(status_code=400, detail="Email already registered")

    db.execute(
        """
        INSERT INTO Employee
        (FirstName, LastName, Email, PhoneNumber, Department, Password, Role)
        VALUES (?, ?, ?, ?, ?, ?, 1);
        """,
        u.first_name, u.last_name, u.email, u.phone, u.department, u.password
    )
    db.execute("SELECT @@IDENTITY;")
    emp_id = db.fetchone()[0]

    return UserOut(
        employee_id=emp_id,
        first_name=u.first_name,
        last_name=u.last_name,
        email=u.email,
        phone=u.phone,
        department=u.department,
        role=1
    )

# --- 4) Create an Admin account ---


@app.post(
    "/users/admin",
    response_model=UserOut,
    status_code=201,
    summary="Create a new Admin (Admin only)"
)
def create_admin(
    u: UserCreate,
    admin: TokenData = Depends(require_admin),
    db=Depends(get_db)
):
    """
    Inserts a new Employee record with role=2 (Admin).
    """
    db.execute("SELECT 1 FROM Employee WHERE Email=?;", u.email)
    if db.fetchone():
        raise HTTPException(status_code=400, detail="Email already registered")

    db.execute(
        """
        INSERT INTO Employee
        (FirstName, LastName, Email, PhoneNumber, Department, Password, Role)
        VALUES (?, ?, ?, ?, ?, ?, 2);
        """,
        u.first_name, u.last_name, u.email, u.phone, u.department, u.password
    )
    db.execute("SELECT @@IDENTITY;")
    emp_id = db.fetchone()[0]

    return UserOut(
        employee_id=emp_id,
        first_name=u.first_name,
        last_name=u.last_name,
        email=u.email,
        phone=u.phone,
        department=u.department,
        role=2
    )

# --- 5) List all users ---


@app.get(
    "/users",
    response_model=List[UserOut],
    summary="List all users (Manager/Admin)"
)
def list_users(
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db)
):
    """
    Managers and Admins can see everyone; employees cannot.
    """
    if current.role == 0:
        raise HTTPException(
            status_code=403, detail="Manager/Admin access required")

    db.execute(
        "SELECT EmployeeID, FirstName, LastName, Email, PhoneNumber, Department, Role "
        "FROM Employee;"
    )
    rows = db.fetchall()
    return [
        UserOut(
            employee_id=r[0],
            first_name=r[1],
            last_name=r[2],
            email=r[3],
            phone=r[4],
            department=r[5],
            role=r[6]
        )
        for r in rows
    ]

# --- 6) Change an existing user’s role ---


@app.put(
    "/users/{emp_id}/role",
    response_model=UserOut,
    summary="Update a user's role (Admin only)"
)
def update_user_role(
    emp_id: int,
    upd: RoleUpdate,
    admin: TokenData = Depends(require_admin),
    db=Depends(get_db)
):
    """
    Set Role = 0 (Employee), 1 (Manager) or 2 (Admin).
    """
    db.execute("SELECT 1 FROM Employee WHERE EmployeeID=?;", emp_id)
    if not db.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    db.execute("UPDATE Employee SET Role=? WHERE EmployeeID=?;",
               upd.role, emp_id)

    db.execute(
        "SELECT EmployeeID, FirstName, LastName, Email, PhoneNumber, Department, Role "
        "FROM Employee WHERE EmployeeID=?;",
        emp_id
    )
    r = db.fetchone()
    return UserOut(
        employee_id=r[0],
        first_name=r[1],
        last_name=r[2],
        email=r[3],
        phone=r[4],
        department=r[5],
        role=r[6]
    )


@app.get(
    "/employee/payrolls/{payroll_id}/pdf",
    response_class=Response,
    summary="Generate payslip PDF (Employee only)"
)
def employee_payslip_pdf(
    payroll_id: int,
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db)
):
    # 1) Verify ownership (or manager/admin)
    db.execute(
        "SELECT EmployeeID FROM Payroll WHERE PayrollID=?;",
        payroll_id
    )
    row = db.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Payroll not found")
    owner_id = row[0]

    # If you’re a plain employee (role=0), you must own this run
    if current.role == 0 and current.employee_id != owner_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 2) Now load the full payroll record
    db.execute(
        "SELECT PayrollDate, ApprovedHours, OvertimeHours, GrossSalary, NetPay "
        "FROM Payroll WHERE PayrollID=?;",
        payroll_id
    )
    pd_row = db.fetchone()
    if not pd_row:
        # (shouldn’t happen, but just in case)
        raise HTTPException(status_code=404, detail="Payroll data missing")

    date, hrs, ot, gross, net = pd_row

    # 3) Employee info
    db.execute(
        "SELECT FirstName, LastName, Email FROM Employee WHERE EmployeeID=?;",
        owner_id
    )
    first, last, email = db.fetchone()

    # 4) Deductions
    db.execute(
        "SELECT DeductionType, Amount FROM Deductions WHERE PayrollID=?;",
        payroll_id
    )
    ded_rows = db.fetchall()
    total_ded = sum(float(r[1]) for r in ded_rows)

    # 5) Build HTML
    html = f"""
    <html><head><meta charset="utf-8"/>
      <style>
        body {{ font-family: sans-serif; padding: 2em }}
        h1 {{ text-align: center; margin-bottom: .5em }}
        table {{ width: 100%; border-collapse: collapse; margin-top:1em }}
        th, td {{ border:1px solid #444; padding:.5em }}
        .right {{ text-align: right }}
      </style>
    </head><body>
      <h1>Payslip</h1>
      <p><strong>Employee:</strong> {first} {last} &lt;{email}&gt;</p>
      <p><strong>Date:</strong> {date}</p>
      <table>
        <tr><th>Description</th><th class="right">Amount</th></tr>
        <tr><td>Gross Salary</td><td class="right">₹{gross:.2f}</td></tr>
        <tr><td>Total Deductions</td><td class="right">-₹{total_ded:.2f}</td></tr>
        <tr><td><strong>Net Pay</strong></td><td class="right"><strong>₹{net:.2f}</strong></td></tr>
      </table>
      <h4>Deductions Detail</h4>
      <table>
        <tr><th>Type</th><th class="right">Amount</th></tr>
        {''.join(f"<tr><td>{dt}</td><td class='right'>₹{amt:.2f}</td></tr>" for dt, amt in ded_rows)}
      </table>
    </body></html>"""

    # 6) Render to PDF
    pdf = HTML(string=html).write_pdf(
        stylesheets=[CSS(string='@page {{ size:A4; margin:1cm }}')]
    )
    return Response(content=pdf, media_type="application/pdf")


@app.get(
    "/employee/payrolls/{payroll_id}/deductions",
    response_model=List[DeductionOut],
    summary="List deductions for one payroll (Employee/Manager/Admin)"
)
def list_employee_deductions(
    payroll_id: int,
    current: TokenData = Depends(get_current_employee),
    db=Depends(get_db)
):
    """
    Employees may only list deductions on *their* payroll runs;
    managers/admins can list any.
    """
    # 1) load the payroll, ensure it exists
    db.execute(
        "SELECT EmployeeID FROM Payroll WHERE PayrollID=?;",
        payroll_id
    )
    row = db.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Payroll not found")

    owner_id = row[0]
    # 2) if employee role (0), block if not their own
    if current.role == 0 and current.employee_id != owner_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 3) fetch deductions
    db.execute(
        "SELECT DeductionID, PayrollID, DeductionType, Amount "
        "FROM Deductions WHERE PayrollID=?;",
        payroll_id
    )
    rows = db.fetchall()
    return [
        DeductionOut(
            deduction_id=r[0],
            payroll_id=r[1],
            deduction_type=r[2],
            amount=float(r[3]),
        )
        for r in rows
    ]
