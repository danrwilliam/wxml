import wxml

@wxml.Ui('code.xml')
class Example6(wxml.ViewModel):
    pass

if __name__ == "__main__":
    wxml.run(Example6)