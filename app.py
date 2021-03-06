from flask import (
    Flask,
    render_template,
    session,
    escape,
    request,
    redirect,
    url_for,
    flash,
)
from dotenv import load_dotenv
import os
import db
from api import Api

load_dotenv(verbose=True)
app = Flask(__name__)
app.secret_key = os.environ["APP_SECRET_KEY"]
cursor = db.connect().cursor()

api = Api(cursor, session)


@app.route("/")
def index():
    """default page"""

    # get all products
    cursor.execute("SELECT * FROM TProduct")
    products = cursor.fetchall()

    if "email" in session:
        return render_template(
            "index.html",
            logged_in=True,
            name=escape(session["name"]),
            email=escape(session["email"]),
            products=products,
        )
    return render_template("index.html", products=products)


@app.route("/search/")
def search_empty():
    """search (when field is empty again)"""

    # get all products
    cursor.execute("SELECT * FROM TProduct")
    products = cursor.fetchall()

    if "email" in session:
        return render_template(
            "partials/products.html",
            logged_in=True,
            name=escape(session["name"]),
            email=escape(session["email"]),
            products=products,
        )
    return render_template("partials/products.html", products=products)


@app.route("/search/<query>")
def search(query):
    """search"""

    cursor.execute("SELECT * FROM TProduct WHERE cName LIKE ?", "%{}%".format(query))
    products = cursor.fetchall()

    return render_template("partials/search.html", query=query, products=products)


@app.route("/advanced_search")
def advanced_search():
    """advanced search"""

    qTitle = request.args.get("qTitle", "")
    qDescription = request.args.get("qDescription", "")

    if qTitle != "" and qDescription == "":
        cursor.execute(
            "SELECT * FROM TProduct WHERE cName LIKE ?", "%{}%".format(qTitle)
        )
    elif qTitle != "" and qDescription != "":
        cursor.execute(
            "SELECT * FROM TProduct WHERE cName LIKE ? AND cDescription LIKE ?",
            "%{}%".format(qTitle),
            "%{}%".format(qDescription),
        )
    elif qTitle == "" and qDescription != "":
        cursor.execute(
            "SELECT * FROM TProduct WHERE cDescription LIKE ?",
            "%{}%".format(qDescription),
        )
    else:
        cursor.execute("SELECT * FROM TProduct")

    products = cursor.fetchall()

    if "email" in session:
        return render_template(
            "advanced_search.html",
            logged_in=True,
            name=escape(session["name"]),
            email=escape(session["email"]),
            products=products,
        )
    return render_template("advanced_search.html", products=products)


@app.route("/checkout")
def checkout():
    """checkout page"""

    if not "email" in session:
        flash(u"You have to log in to make purchases.", "info")
        return redirect(url_for("login"))
    checkoutItems = api.get_unique_products()
    numberOfItems = len(checkoutItems)
    usersCreditCards = api.get_credit_cards_from_email(escape(session["email"]))
    total = 0
    for i in range(0, len(checkoutItems)):
        total = total + checkoutItems[i][2]
    return render_template(
        "checkout.html",
        logged_in=True,
        name=escape(session["name"]),
        email=escape(session["email"]),
        checkoutItems=checkoutItems,
        usersCreditCards=usersCreditCards,
        numberOfItems=numberOfItems,
        total=total,
    )


@app.route("/buy", methods=["POST"])
def buy():
    """buy (finish purchase)"""

    if not "email" in session:
        flash(u"You have to log in to make purchases.", "info")
        return redirect(url_for("login"))

    checkoutItems = api.get_unique_products()
    creditCardNo = request.form["creditCardNo"]

    print(checkoutItems)

    for product in checkoutItems:
        itemStockQty = product[0][4]
        itemCartAmount = product[1]
        productName = product[0][1]
        if(itemStockQty < itemCartAmount):
            flash(u"Purchase Cancelled! Sorry, we currently only have " 
            + str(itemStockQty) + " of " 
            + productName, "Error")
            return redirect(url_for("index"))

    # create a new invoice
    api.create_invoice(session["id"], checkoutItems, creditCardNo, 20)

    # clear cart
    session["cartProduct"] = []

    flash(u"Thanks for your purchase.", "success")
    return redirect(url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """log in"""

    if request.method == "POST":
        email = request.form["email"]

        # get users FROM database with this email
        cursor.execute(
            """
            SELECT iUserId, cEmail, cFirstName, cLastName
            FROM TUser
            WHERE cEmail = ?
            """,
            email
        )
        users = cursor.fetchall()

        if len(users) < 1:
            flash(u"A user with this email could not be found.", "danger")
            return render_template("login.html")
        user = users[0]
        session["id"] = user.iUserId
        session["email"] = user.cEmail
        session["name"] = "{} {}".format(user.cFirstName, user.cLastName)
        return redirect(url_for("index"))

    cursor.execute("SELECT cEmail FROM TUser;")
    emails = [x.cEmail for x in cursor.fetchall()]

    return render_template("login.html", emails=emails)


@app.route("/logout")
def logout():
    """log out"""

    session.pop("email", None)
    session.pop("name", None)
    flash(u"You've been logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route("/db_check")
def db_check():
    """show the database connection information"""

    # Sample SELECT query
    cursor.execute("SELECT @@version;")
    version = []
    row = cursor.fetchone()
    while row:
        version.append(row[0])
        row = cursor.fetchone()
    return render_template("db_check.html", version="\n".join(version))


@app.route("/cart")
def cart():
    """show the cart page"""

    if "cartProduct" not in session:
        session["cartProduct"] = []
    shoppingCart = api.get_unique_products()
    numberOfItems = len(shoppingCart)

    total = 0
    for i in range(0, len(shoppingCart)):
        total = total + shoppingCart[i][2]

    if "email" in session:
        return render_template(
            "cart.html",
            logged_in=True,
            name=escape(session["name"]),
            email=escape(session["email"]),
            haspurchases=True,
            cartProduct=shoppingCart,
            numberOfItems=numberOfItems,
            total=total,
        )
    else:
        return render_template(
            "cart.html",
            logged_in=False,
            haspurchases=True,
            cartProduct=shoppingCart,
            numberOfItems=numberOfItems,
            total=total,
        )


##################################################################################
# api
##################################################################################
@app.route("/api/cart", methods=["POST"])
def cart_add():
    """add a product to the cart"""

    if "cartProduct" not in session:
        session["cartProduct"] = []
    tempCart = session["cartProduct"]
    json = request.get_json()
    print(json)
    productId = json["productId"]
    amount = int(json["amount"])

    for i in range(amount):
        tempCart.append(productId)

    session["cartProduct"] = tempCart
    return "success"


@app.route("/api/cart", methods=["DELETE"])
def cart_delete():
    """remove a product FROM the cart"""

    tempCart = session["cartProduct"]
    productId = request.get_json()
    tempCart.remove(productId)
    session["cartProduct"] = tempCart
    return "succes"


@app.route("/api/products/<int:product_id>/ratings")
def product_ratings(product_id):
    """get all ratings for a product"""
    cursor.execute(
        """
        SELECT * FROM TRating
        INNER JOIN TUser ON TRating.iUserId = TUser.iUserId
        WHERE iProductId = ?
        """,
        product_id,
    )

    ratings = cursor.fetchall()
    return render_template(
        "partials/ratings.html", ratings=ratings, product_id=product_id
    )


@app.route("/api/products/<int:product_id>/ratings", methods=["POST"])
def rate(product_id):
    """rate a product"""

    if "email" in session:
        id = session["id"]
        rating = request.form["rating"]
        comment = request.form["comment"]

        cursor.execute(
            """
            INSERT INTO TRating (iProductId, iUserId, iRating, cComment) 
            VALUES ( ? , ? , ? , ? )
            """,
            product_id,
            id,
            rating,
            comment,
        )
        cursor.commit()

        flash(u"Your rating has been saved.", "success")
        return redirect(url_for("index"))

    else:
        flash(u"Please log in to rate a product.", "danger")
        return redirect(url_for("index"))


##################################################################################
# custom filters
###################################################################################


@app.template_filter()
def dkk(value):
    """custom flask filter to style currency in dkk"""
    return "{:.2f} kr.".format(value)
