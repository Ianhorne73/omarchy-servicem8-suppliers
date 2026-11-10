"""Synthetic desktop check of typed confirmation. Never calls ServiceM8."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

@unittest.skipUnless(os.environ.get('RUN_QML_INTEGRATION') == '1' and shutil.which('qs'), 'Set RUN_QML_INTEGRATION=1 in an Omarchy desktop session')
class DeleteUiTests(unittest.TestCase):
    def test_confirmation_cancel_failure_and_success(self):
        with tempfile.TemporaryDirectory(prefix='supplier-delete-ui-') as tmp:
            root=Path(tmp)
            for name in ('Commons','Ui'):
                (root/name).symlink_to(Path('/usr/share/omarchy/shell')/name,target_is_directory=True)
            plugin=root/'plugin';plugin.mkdir()
            source=Path(__file__).parent
            shutil.copy2(source/'BarWidget.qml',plugin/'BarWidget.qml')
            shutil.copytree(source/'i18n',plugin/'i18n')
            (plugin/'suppliers.py').write_text('''import json,sys
assert sys.argv[1:] == ['--delete']
p=json.load(sys.stdin)
assert p['confirmation']=='yes'
if p['name']=='Fail supplier': print(json.dumps({'deleted':False,'error_code':'deletePermission'}))
else: print(json.dumps({'deleted':True,'report':{'suppliers':[],'error':'','connected':True}}))
''')
            (root/'shell.qml').write_text('''import QtQuick
import Quickshell
ShellRoot {
 id: test
 property int stage: 0
 property int ticks: 0
 function child(item,name,seen) {
  if(!item)return null
  seen=seen || []
  if(seen.indexOf(item)>=0)return null
  seen.push(item)
  if(item.objectName===name)return item
  var keys=["data","children","contentItem"]
  for(var k=0;k<keys.length;k++) {
   var nodes=item[keys[k]]
   if(!nodes)continue
   if(nodes.length===undefined)nodes=[nodes]
   for(var i=0;i<nodes.length;i++){var found=child(nodes[i],name,seen);if(found)return found}
  }
  return null
 }
 function check(condition,message){if(!condition){console.log("TEST_FAILED: "+message);Qt.quit()}}
 Loader {
  id: loader
  source: "plugin/BarWidget.qml"
  onLoaded: {
   var row={uuid:"00000000-0000-4000-8000-000000000001",name:"Fail supplier",email:"orders@example.invalid",address:"Line 1"}
   item.report={suppliers:[row],error:""}
   item.startDelete(row)
   var field=test.child(item,"deleteConfirmation")
   var button=test.child(item,"confirmDelete")
   var bad=["","Yes","YES"," yes","yes ","yesterday"]
   for(var i=0;i<bad.length;i++){
    field.text=bad[i]
    test.check(!button.enabled,"invalid text must disable delete")
    item.confirmDelete()
    test.check(!item.busy,"invalid text must not call helper")
   }
   field.text="yes"
   test.check(button.enabled,"exact yes must enable delete")
   item.cancelDelete()
   test.check(!item.deleteVisible && field.text==="","cancel clears confirmation")
   item.startDelete(row)
   test.check(field.text==="" && !button.enabled,"reopening requires fresh confirmation")
   field.text="yes"
   item.confirmDelete()
  }
 }
 Timer {
  interval:100;running:true;repeat:true
  onTriggered:{
   test.ticks++
   if(test.ticks>80){console.log("TEST_FAILED: timeout");Qt.quit();return}
   var widget=loader.item
   if(!widget || widget.busy)return
   var field=test.child(widget,"deleteConfirmation")
   if(test.stage===0 && widget.deleteErrorCode==="deletePermission"){
    test.check(widget.deleteVisible,"failure keeps confirmation screen")
    test.check(field.text==="","failure requires typing yes again")
    test.check(widget.report.suppliers.length===1,"failure keeps supplier")
    test.stage=1
    widget.startDelete({uuid:"00000000-0000-4000-8000-000000000002",name:"Example Supplier"})
    test.check(field.text==="","new target requires fresh confirmation")
    field.text="yes"
    widget.confirmDelete()
   }else if(test.stage===1 && widget.noticeCode==="deleteSaved"){
    test.check(!widget.deleteVisible,"success dismisses confirmation")
    test.check(widget.report.suppliers.length===0,"success updates supplier list")
    test.check(field.text==="","success clears confirmation")
    console.log("DELETE_UI_OK")
    Qt.quit()
   }
  }
 }
}
''')
            result=subprocess.run(['qs','-p',str(root),'--no-color'],capture_output=True,text=True,timeout=15)
            output=result.stdout+result.stderr
            self.assertNotIn('TEST_FAILED',output,output)
            self.assertIn('DELETE_UI_OK',output,output)
            self.assertNotIn('ReferenceError',output,output)
            self.assertNotIn('TypeError',output,output)

if __name__=='__main__': unittest.main()
