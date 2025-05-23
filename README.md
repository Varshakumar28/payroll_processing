# payroll_processing
## Project Overview
The Employee Timesheet and Payroll System is designed to help organizations efficiently manage employee work hours, track attendance, and automate payroll calculations. It stores employee details, logs work hours, computes salaries based on different pay structures and generates pay slips while ensuring accuracy and compliance with company policies on overtime, leaves, and deductions.
## Project Objectives
•	Develop an MS Access-based system to manage employee timesheets and payroll processing.
•	Utilize SQL for database operations like employee record management, salary computation, and report generation.
•	Implement automated calculations for overtime pay, tax deductions, and benefits.

## structure 

``` 
payroll-app/
│
├── app/
│   ├── main.py
│   ├── auth.py
│   ├── payroll_logic.py
│   ├── database.py
│   └── models/
│
├── docs/
│   ├── presentation.pdf
│   ├── architecture.png
│   └── database_schema.png
│
├── requirements.txt
├── README.md
└── .gitignore
```
##  Feature	Description: 
1. Role-Based Access Control - Users assigned as Employee (0), Manager (1), or Admin (2)
2. Timesheet Submission	- Employees log daily work hours
3.  Manager Approvals -	Managers review and approve employee logs
4.  Payroll Calculations -	HR generates salary after deductions
5. PDF Generation- 	Auto-generates salary slips in PDF format
6.  Swagger / ReDoc Docs	- Interactive testing and clean API documentation

## Technologies & Tools i have used in this project: 
For: 
1. Backend Framework - 	FastAPI
2. Language	- Python
3. Database -	MS Access
4. DB Connector	- pyodbc
5. Authentication	- JWT (JSON Web Tokens)
6. API Docs	- Swagger UI, ReDoc
7. PDF Generator -	Python PDF libraries
8. IDE	- VSCode

## My Database Schema
<img width="501" alt="image" src="https://github.com/user-attachments/assets/25c815b4-b3b0-4bcb-bc50-3adeb1cfe636" />

## for Live Documentation
1. Swagger UI: http://127.0.0.1:8001/docs
↳ Enables live API testing

2. ReDoc: http://127.0.0.1:8001/redoc
↳ Clean developer documentation

## key learning
Throughout this project, I gained hands-on experience in building secure, RESTful APIs using FastAPI, which deepened my understanding of modern web backend frameworks. I implemented JWT-based authentication with role-based access control (RBAC), ensuring that different user roles—Employee, Manager, and Admin—could securely interact with the system. I also learned how to connect and interact with legacy databases using ODBC drivers, specifically integrating Microsoft Access with Python via the pyodbc library. Designing and documenting APIs using Swagger and ReDoc allowed me to appreciate the importance of interactive and readable documentation for developer usability. Additionally, I explored dynamic PDF generation in Python, which was crucial for generating payroll slips. I emphasized modular backend design and clean separation of concerns to improve code maintainability. 

## License
This project is licensed under the MIT License.

## Author
Varsha Medukonduru — Graduate student specialising in Business Analytics & Data Engineering. 
