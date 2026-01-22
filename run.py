from src import	create_app
from src.cyclic_manager import check_and_process_cyclic_transactions

app = create_app()

if __name__ == "__main__":
    check_and_process_cyclic_transactions(app)
    app.run(debug = True)
