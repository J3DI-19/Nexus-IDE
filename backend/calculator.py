from math_utils import add, subtract, multiply, divide


def main():
    print("Simple Calculator")

    a = float(input("Enter first number: "))
    b = float(input("Enter second number: "))

    operation = input("Choose (+, -, *, /): ")

    if operation == "+":
        result = add(a, b)
    elif operation == "-":
        result = subtract(a, b)
    elif operation == "*":
        result = multiply(a, b)
    elif operation == "/":
        result = divide(a, b)
    else:
        print("Invalid operation")
        return

    print("Result:", result)


if __name__ == "__main__":
    main()
