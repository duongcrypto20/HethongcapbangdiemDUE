from app import app

# Vercel đòi hỏi file entry point xuất ra đối tượng app
if __name__ == '__main__':
    app.run()