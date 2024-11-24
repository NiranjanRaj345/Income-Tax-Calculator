"""Create sample employee accounts."""
from app import create_app
from models import db, Employee
import random

# List of sample first names and last names
first_names = [
    "John", "Emma", "Michael", "Sarah", "David",
    "Lisa", "James", "Emily", "Robert", "Jessica"
]

last_names = [
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"
]

def create_sample_employees():
    """Create 10 sample employee accounts."""
    app = create_app()
    
    with app.app_context():
        # Create 10 employees
        for i in range(10):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            email = f"{first_name.lower()}.{last_name.lower()}@example.com"
            
            # Check if employee already exists
            if not Employee.query.filter_by(email=email).first():
                employee = Employee(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    phone=f"555-{random.randint(1000, 9999)}",
                    is_active=True
                )
                employee.set_password('employee123')  # Same password for all employees
                db.session.add(employee)
                print(f"Created employee: {first_name} {last_name} ({email})")
            else:
                print(f"Employee {email} already exists!")
        
        db.session.commit()
        print("\nAll employees created successfully!")
        print("Default password for all employees: employee123")

if __name__ == '__main__':
    create_sample_employees()
