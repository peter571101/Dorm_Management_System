from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import pymysql
from pymysql import cursors

app = Flask(__name__)
app.secret_key = "your_secret_key"


# 数据库连接
def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='gld131571314',
        database='dorm_management',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


# 初始化数据库
def init_db():
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='gld131571314',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with connection.cursor() as cursor:
            # 创建数据库
            cursor.execute("CREATE DATABASE IF NOT EXISTS dorm_management")
            cursor.execute("USE dorm_management")
            # 创建管理员表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    admin_id VARCHAR(20) PRIMARY KEY,
                    password VARCHAR(100) NOT NULL
                )
            """)
            # 创建学生表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    student_id VARCHAR(20) PRIMARY KEY,
                    name VARCHAR(50) ,
                    password VARCHAR(100) ,
                    id_card CHAR(18)  UNIQUE,      -- 新增身份证号（18位，唯一）
                    gender CHAR(2)  CHECK (gender IN ('男', '女')),  -- 新增性别（M男/F女）
                    s_class VARCHAR(50) ,           -- 新增班级（如 "计算机2023级1班"）
                    building_number VARCHAR(20),
                    building_name VARCHAR(50), 
                    room_number VARCHAR(20)
                )
            """)
            # 创建宿舍表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS buildings (
                    building_id INT AUTO_INCREMENT PRIMARY KEY,
                    building_number VARCHAR(20) NOT NULL,
                    building_name VARCHAR(50) NOT NULL,
                    UNIQUE INDEX unique_combo (building_number, building_name)
                )
            """)
            # 创建报修表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repair_requests (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id VARCHAR(20) NOT NULL,
                    description TEXT NOT NULL,
                    status ENUM('待处理', '已处理') DEFAULT '待处理',
                    response TEXT,
                    FOREIGN KEY (student_id) REFERENCES students(student_id)
                )
            """)
            # 插入测试楼宇数据
            cursor.execute("INSERT IGNORE INTO buildings (building_number, building_name) VALUES ('9', '东苑')")
            cursor.execute("INSERT IGNORE INTO buildings (building_number, building_name) VALUES ('2', '西苑')")
            # 插入测试管理员账号
            cursor.execute("INSERT IGNORE INTO admins (admin_id, password) VALUES ('admin', 'admin123')")
            # 插入测试学生账号
            cursor.execute("INSERT IGNORE INTO students (student_id, name, password, id_card, gender, s_class, "
                           "building_number, building_name, room_number) VALUES ('12', '史俊杰', '123',"
                           "'320275202503092612','男','经管1703', '2', '西苑', '3')")
        connection.commit()
    finally:
        connection.close()


# 在应用启动时初始化数据库
init_db()


@app.route('/admin/building/<building_name><building_number>栋')
def admin_building_students(building_number, building_name):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 查询楼宇名称
            sql = "SELECT building_name FROM buildings WHERE building_number = %s AND building_name = %s"
            cursor.execute(sql, (building_number, building_name))
            building = cursor.fetchone()

            # 查询该楼宇的学生信息（按房间号分组）
            sql = """
                SELECT room_number, GROUP_CONCAT(name SEPARATOR ', ') AS students
                FROM students
                WHERE building_number = %s AND building_name = %s
                GROUP BY room_number
            """
            cursor.execute(sql, (building_number, building_name))
            students = cursor.fetchall()
    except Exception as e:
        error = f"查询失败：{str(e)}"
        return render_template('error.html', error=error)
    finally:
        connection.close()

    return render_template('admin_building_students.html', building=building, students=students)


@app.route('/admin/update_building/<building_id>', methods=['GET', 'POST'])
def admin_update_building(building_id):
    # 检查用户是否已登录且为管理员
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()
    error = None
    success = None
    warning = None

    try:
        with connection.cursor() as cursor:
            # 获取原始数据（包含主键 id）
            cursor.execute(
                "SELECT * FROM buildings WHERE building_id = %s",
                (building_id,)
            )
            original_data = cursor.fetchone()
            if not original_data:
                flash('楼宇不存在', 'error')
                return redirect(url_for('admin_buildings'))

            if request.method == 'POST':
                new_number = request.form['building_number'].strip()
                new_name = request.form['building_name'].strip()

                # 检查是否有修改
                if new_number == original_data['building_number'] and new_name == original_data['building_name']:
                    warning = "未检测到任何修改，无需更新。"
                    return render_template('admin_update_building.html',
                                           building=original_data,
                                           warning=warning)

                # 验证新组合是否唯一（排除自身）
                cursor.execute(
                    """SELECT * FROM buildings 
                       WHERE building_number = %s 
                         AND building_name = %s 
                         AND building_id != %s""",
                    (new_number, new_name, original_data['building_id'])
                )
                if cursor.fetchone():
                    error = f"{new_name}{new_number}栋已存在"
                    return render_template('admin_update_building.html',
                                           building=original_data,
                                           error=error)

                # 执行更新（通过主键定位）
                cursor.execute(
                    """UPDATE buildings 
                       SET building_number = %s, building_name = %s 
                       WHERE building_id = %s""",
                    (new_number, new_name, original_data['building_id'])
                )

                # 同步更新学生表
                cursor.execute(
                    """UPDATE students 
                       SET building_number = %s, building_name = %s 
                       WHERE building_number = %s AND building_name = %s""",
                    (new_number, new_name, original_data['building_number'], original_data['building_name'])
                )

                connection.commit()
                success = "楼宇信息更新成功！"

                # 获取更新后的数据
                cursor.execute(
                    "SELECT * FROM buildings WHERE building_id = %s",
                    (original_data['building_id'],)
                )
                updated_data = cursor.fetchone()

                return render_template('admin_update_building.html',
                                       building=updated_data,
                                       success=success)

            else:
                # GET 请求，直接渲染页面
                return render_template('admin_update_building.html',
                                       building=original_data)

    except Exception as e:
        if connection:
            connection.rollback()
        error = f"操作失败：{str(e)}"
        return render_template('admin_update_building.html',
                               building=original_data,
                               error=error)
    finally:
        if connection:
            connection.close()


# 增加宿舍樓
@app.route('/admin/add_building', methods=['GET', 'POST'])
def admin_add_building():
    # 检查用户权限
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))

    connection = None
    error = None
    success = None
    warning = None

    try:
        if request.method == 'POST':
            new_number = request.form['building_number'].strip()
            new_name = request.form['building_name'].strip()

            # 输入空值验证
            if not new_number or not new_name:
                warning = "楼宇编号和名称不能为空！"
                return render_template('admin_add_building.html',
                                       warning=warning)

            connection = get_db_connection()
            with connection.cursor() as cursor:
                # 检查编号唯一性
                cursor.execute(
                    "SELECT * FROM buildings WHERE building_number = %s AND building_name = %s",
                    (new_number, new_name,)
                )
                if cursor.fetchone():
                    error = f" {new_name}{new_number}栋 已存在！"
                    return render_template('admin_add_building.html',
                                           error=error)

                # 插入新楼宇
                cursor.execute(
                    "INSERT INTO buildings (building_number, building_name) VALUES (%s, %s)",
                    (new_number, new_name)
                )
                connection.commit()
                success = "楼宇添加成功"

        return render_template('admin_add_building.html',
                               success=success,
                               error=error,
                               warning=warning)

    except pymysql.IntegrityError as e:
        error = "数据库唯一性约束冲突：" + str(e)
        return render_template('admin_add_building.html',
                               error=error)
    except Exception as e:
        error = f"系统错误：{str(e)}"
        if connection:
            connection.rollback()
        return render_template('admin_add_building.html',
                               error=error)
    finally:
        if connection:
            connection.close()


# 首页
@app.route('/')
def index():
    return redirect(url_for('login'))


# 注册页面
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        student_id = request.form['student_id']
        name = request.form['name']
        password = request.form['password']
        id_card = request.form['id_card']
        gender = request.form['gender']
        s_class = request.form['s_class']
        building_number = request.form['building_number']
        building_name = request.form['building_name']
        room_number = request.form['room_number']

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # 检查楼宇是否存在
                sql = "SELECT * FROM buildings WHERE building_number = %s AND building_name = %s"
                cursor.execute(sql, (building_number, building_name))
                building = cursor.fetchone()
                if not building:
                    flash('楼宇名称或楼宇编号不存在！', 'error')
                    return redirect(url_for('register'))

                # 插入学生信息
                sql = """INSERT INTO students (student_id, name, password, id_card, gender, s_class, building_number, 
                building_name, room_number) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
                cursor.execute(sql, (student_id, name, password, id_card, gender, s_class, building_number, building_name, room_number))
            connection.commit()
            flash('注册成功！请登录。', 'success')
            return redirect(url_for('login'))
        except pymysql.IntegrityError:
            flash('学号已存在！', 'error')
        finally:
            connection.close()
    return render_template('register.html')


# 登录页面
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        user_type = request.form['user_type']

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                if user_type == 'student':
                    sql = "SELECT * FROM students WHERE student_id = %s AND password = %s"
                else:
                    sql = "SELECT * FROM admins WHERE admin_id = %s AND password = %s"
                cursor.execute(sql, (user_id, password))
                user = cursor.fetchone()
                if user:
                    session['user_id'] = user_id
                    session['user_type'] = user_type
                    return redirect(url_for('student_home' if user_type == 'student' else 'admin_home'))
                else:
                    flash('用户名或密码错误！', 'error')
        finally:
            connection.close()
    return render_template('login.html')


# 学生主页
@app.route('/student/home')
def student_home():
    if 'user_id' not in session or session['user_type'] != 'student':
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 查询学生的姓名
            sql = "SELECT name FROM students WHERE student_id = %s"
            cursor.execute(sql, (session['user_id'],))
            student = cursor.fetchone()
            if student:
                name = student['name']
            else:
                name = "未知用户"
    finally:
        connection.close()

    return render_template('student_home.html', name=name)


# 学生个人信息
@app.route('/student/profile', methods=['GET', 'POST'])
def student_profile():
    if 'user_id' not in session or session['user_type'] != 'student':
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 查询学生信息
            sql = "SELECT * FROM students WHERE student_id = %s"
            cursor.execute(sql, (session['user_id'],))
            student = cursor.fetchone()
    finally:
        connection.close()

    return render_template('student_profile.html', student=student)


# 学生报修
@app.route('/student/repair', methods=['GET', 'POST'])
def student_repair():
    if 'user_id' not in session or session['user_type'] != 'student':
        return redirect(url_for('login'))

    if request.method == 'POST':
        description = request.form['description']
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                sql = "INSERT INTO repair_requests (student_id, description) VALUES (%s, %s)"
                cursor.execute(sql, (session['user_id'], description))
            connection.commit()
            flash('报修信息已提交！', 'success')
        finally:
            connection.close()
    return render_template('student_repair.html')


# 管理员主页
@app.route('/admin/home')
def admin_home():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    return render_template('admin_home.html')


# 楼宇信息页面
@app.route('/admin/buildings')
def admin_buildings():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 查询所有楼宇
            sql = "SELECT * FROM buildings"
            cursor.execute(sql)
            buildings = cursor.fetchall()
    finally:
        connection.close()

    return render_template('admin_buildings.html', buildings=buildings)


# 管理学生信息
@app.route('/admin/students', methods=['GET', 'POST'])
def admin_students():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            if request.method == 'POST':
                action = request.form['action']
                student_id = request.form['student_id']
                if action == 'delete':
                    sql = "DELETE FROM students WHERE student_id = %s"
                    cursor.execute(sql, (student_id,))
                elif action == 'update':
                    name = request.form['name']
                    id_card = request.form['id_card']
                    gender = request.form['gender']
                    s_class = request.form['s_class']
                    building_number = request.form['building_number']
                    building_name = request.form['building_name']
                    room_number = request.form['room_number']
                    sql = ("UPDATE students SET name = %s, id_card = %s, gender = %s, s_class = %s, "
                           "building_number = %s, building_name = %s, room_number = %s "
                           "WHERE student_id = %s")
                    cursor.execute(sql, (name, id_card, gender, s_class, building_number, building_name, room_number, student_id))
                connection.commit()

            sql = "SELECT * FROM students"
            cursor.execute(sql)
            students = cursor.fetchall()
    finally:
        connection.close()
    return render_template('admin_students.html', students=students)

# 管理报修信息
@app.route('/admin/repairs', methods=['GET', 'POST'])
def admin_repairs():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            if request.method == 'POST':
                repair_id = request.form['repair_id']
                response = request.form['response']
                status = request.form['status']
                sql = "UPDATE repair_requests SET response = %s, status = %s WHERE id = %s"
                cursor.execute(sql, (response, status, repair_id))
                connection.commit()

            sql = """
                            SELECT 
                                r.*, 
                                s.name, 
                                s.building_number, 
                                s.room_number, 
                                b.building_name 
                            FROM 
                                repair_requests r 
                            JOIN 
                                students s ON r.student_id = s.student_id 
                            JOIN 
                                buildings b ON s.building_number = b.building_number
                        """
            cursor.execute(sql)
            repairs = cursor.fetchall()
    finally:
        connection.close()
    return render_template('admin_repairs.html', repairs=repairs)


# 管理员修改密码页面
@app.route('/admin/change_password', methods=['GET'])
def change_password_page_admin():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    return render_template('admin_change_password.html')


# 处理管理员修改密码请求
@app.route('/admin/change_password', methods=['POST'])
def admin_change_password():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return jsonify({"success": False, "message": "未登录或无权访问"}), 401

    # 获取表单数据
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # 检查新密码和确认密码是否一致
    if new_password != confirm_password:
        return jsonify({"success": False, "message": "新密码与确认密码不一致"}), 400

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 验证旧密码
            sql = "SELECT password FROM admins WHERE admin_id = %s"
            cursor.execute(sql, (session['user_id'],))
            admin = cursor.fetchone()
            if not admin or admin['password'] != old_password:
                return jsonify({"success": False, "message": "旧密码错误"}), 400

            # 更新密码
            sql = "UPDATE admins SET password = %s WHERE admin_id = %s"
            cursor.execute(sql, (new_password, session['user_id']))
        connection.commit()
        session.clear()  # 清除会话信息，强制重新登录
        return jsonify({"success": True, "message": "密码修改成功"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"数据库操作失败：{str(e)}"}), 500
    finally:
        connection.close()


# 学生修改密码页面
@app.route('/student/change_password', methods=['GET'])
def change_password_page_student():
    if 'user_id' not in session or session['user_type'] != 'student':
        return redirect(url_for('login'))
    return render_template('student_change_password.html')


# 处理学生修改密码请求
@app.route('/student/change_password', methods=['POST'])
def student_change_password():
    if 'user_id' not in session or session['user_type'] != 'student':
        return jsonify({"success": False, "message": "未登录或无权访问"}), 401

    # 获取表单数据
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # 检查新密码和确认密码是否一致
    if new_password != confirm_password:
        return jsonify({"success": False, "message": "新密码与确认密码不一致"}), 400

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 验证旧密码
            sql = "SELECT password FROM students WHERE student_id = %s"
            cursor.execute(sql, (session['user_id'],))
            student = cursor.fetchone()
            if not student or student['password'] != old_password:
                return jsonify({"success": False, "message": "旧密码错误"}), 400

            # 更新密码
            sql = "UPDATE students SET password = %s WHERE student_id = %s"
            cursor.execute(sql, (new_password, session['user_id']))
        connection.commit()
        session.clear()  # 清除会话信息，强制重新登录
        return jsonify({"success": True, "message": "密码修改成功"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"数据库操作失败：{str(e)}"}), 500
    finally:
        connection.close()


# 注销
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
