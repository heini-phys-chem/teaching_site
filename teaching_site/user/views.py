from teaching_site import app, db, mail, send_email
from flask import render_template, redirect, url_for, flash, session, abort, request
from teaching_site.user.form import RegisterForm, LoginForm, ValidationForm, LostForm
from teaching_site.user.models import User
from teaching_site.user.decorators import login_required, only_from
import bcrypt
from random import choice
import string
from numpy.random import randint
from datetime import datetime

def login_user(user):
    session['username'] = user.username
    session['is_admin'] = user.is_admin

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    error = None
    if request.method=='GET' and request.args.get('next'):
        session['next'] = request.args.get('next', None)
    if form.validate_on_submit():
        user = User.query.filter_by(
            username=form.username.data,
        ).first()
        if user:
            if user.password != '':
                try:
                    password_in = bcrypt.hashpw(
                        form.password.data, user.password
                    )
                except TypeError:
                    password_in = ''
            else:
                password_in = form.password.data
            if password_in == user.password \
            or form.password.data == user.password_tmp:
                # set session variable username when login
                login_user(user)
                if form.password.data == user.password_tmp:
                    user.password_tmp = ''
                    db.session.commit()
                    flash('temporary password expired')
                    flash('please reset your password')
                    return redirect(url_for('user_setting'))
                if not user.validated:
                    return redirect(url_for('validate'))
                if 'next' in session:
                    next = session.get('next')
                    session.pop('next')
                    return redirect(next)
                else:
                    flash("login as %s" % session['username'])
                    return redirect(url_for('index'))
            else:
                error = "Incorrect username or password"
        else:
            error = "Incorrect username or password"
    return render_template('user/login.html', form=form, error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    error = ""
    if form.validate_on_submit():
        salt = bcrypt.gensalt()
        hashedpw = bcrypt.hashpw(form.password.data, salt)

        # check register list
        # check admin
        # get random seed
        is_admin = False
        validated = False

        user_new = User(
            form.fullname.data,
            form.email.data,
            form.username.data,
            hashedpw,
            is_admin,
            validated,
        )

        user_old = User.query.filter_by(
            email=form.email.data,
        ).first()

        if user_old:
            if user_old.validated:
                error = "email: %s already registered" % user_new.email
                return render_template(
                    'user/register.html', 
                    form=form, error=error
                )
            else:
                user_old.fullname = user_new.fullname
                user_old.username = user_new.username
                user_old.password = hashedpw
                session['username'] = user_new.username
                session['is_admin'] = user_new.is_admin
                db.session.commit()
                send_validation_email()
                return redirect(url_for('validate'))

        try:
            db.session.add(user_new)
            db.session.flush()
        except:
            error = "username: %s is already taken" % user_new.username
            return render_template(
                'user/register.html', 
                form=form, error=error
            )

        if user_new.id:
            db.session.commit()
            flash("User %s created" % form.username.data)
            session['username'] = form.username.data
            session['is_admin'] = is_admin
            send_validation_email()
            return redirect(url_for('validate'))
        else:
            db.session.rollback()
            error = "Error creating user, please contact administrator"
    return render_template('user/register.html', form=form, error=error)

@app.route('/validate', methods=['GET', 'POST'])
@login_required
def validate():
    form = ValidationForm()
    error = ""
    user = User.query.filter_by(
        username=session['username'],
    ).first()
    user_id = user.id
    if user.validated:
        return redirect(url_for('index'))
    if form.validate_on_submit():
        validate_input = form.validation_code.data
        if validate_input == user.validation_code:
            user.validated = True
            db.session.commit()
            return redirect(url_for('index'))
    return render_template(
        'user/validate.html', 
        form=form, user=user, user_id=user_id, error = error
    )
    
@app.route('/send_validate_email')
@login_required
@only_from('validate', 'register')
def send_validation_email():
    user = User.query.filter_by(
        username=session['username'],
    ).first()
    title = "Validation code"
    text_list = [
        "Welcome %s\n\n" % user.fullname,
        "Your validation code is: %s\n" % user.validation_code,
    ]
    body = ''.join(text_list)
    send_email(user.email, title, body)
    flash('sending validation email to %s' % user.email)
    return redirect(url_for('validate'))

@app.route('/lost_password', methods=['GET', 'POST'])
@only_from('login', 'lost_password')
def lost_password():
    form = LostForm()
    error = ""
    if form.validate_on_submit():
        user = User.query.filter_by(
            email = form.email.data
        ).first()
        msg = "%s: request for lost password reset for email:%s" %\
              (datetime.now().strftime("%Y/%m/%d-%H:%M:%S"),
               user.email)
        msg += ", from IP: %s" % request.remote_addr
        app.logger.warning(msg)
        if user:
            if user.is_admin:
                flash('no password reset for admin users for se')
                return render_template('user/lost.html', form=form)
            if user.validated:
                alphanum = string.letters + string.digits
                password_new = ''.join(choice(alphanum) \
                    for _ in range(8))
                user.password_tmp = password_new
                db.session.commit()
     
                title = 'Reset password'
                body = 'Hi %s,\n\n Your temporary password is: %s\n'\
                    % (user.fullname, password_new)
                send_email(user.email, title, body)
            flash('inscruction has been sent')
        flash('no email found')
    return render_template('user/lost.html', form=form)

@app.route('/logout')
@login_required
def logout():
    username = session['username']
    session.pop('username')
    if 'is_admin' in session:
        session.pop('is_admin')
    flash('logged out from user: %s' % username)
    return redirect(url_for('index'))

@app.route('/user_setting', methods=['GET', 'POST'])
@login_required
def user_setting():
    user = User.query.filter_by(
        username = session['username'],
    ).first()
    if user.validated:
        form = RegisterForm(obj=user)
        error = ''
        if form.validate_on_submit():
            salt = bcrypt.gensalt()
            hashedpw = bcrypt.hashpw(form.password.data, salt)
            if user.username != form.username.data:
                user.username = form.username.data
                session['username'] = user.username
                flash('loged in as %s' % user.username)
            user.fullname = form.fullname.data
            user.password = hashedpw
            try:
                db.session.commit()
                flash('user data updated')
                msg = "%s: user update for email:%s" %\
                      (datetime.now().strftime("%Y/%m/%d-%H:%M:%S"),
                       user.email)
                msg += ", new username: %s" % user.username
                app.logger.warning(msg)
            except:
                error = 'new username %s is already taken' % \
                    form.username.data
        return render_template('user/user_setting.html', 
            form=form, error=error, user=user
        )
    else:
        return redirect(url_for('validate'))
