# This Python file uses the following encoding: utf-8
'''
BabelBrain: Application for the planning and delivery of LIFU to be triggered from Brainsight
ABOUT:
    author        - Samuel Pichardo
    date          - July 16, 2022
    last update   - July 16, 2022
'''
import multiprocessing
multiprocessing.freeze_support()
from multiprocessing import Process,Queue
import sys
if sys.platform =='linux':
    try:
        multiprocessing.set_start_method('spawn')
    except RuntimeError:
        pass


import os
import shutil
from pathlib import Path

sys.path.append(os.path.abspath('../'))
sys.path.append(os.path.abspath('./'))


from PySide6.QtWidgets import (QApplication, QWidget,QDoubleSpinBox,
                QVBoxLayout,QLineEdit,QDialog,QHBoxLayout,
                QGridLayout, QInputDialog,
                QMessageBox,QProgressBar)
from PySide6.QtCore import QFile,Slot,QObject,Signal,QThread,Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QPalette, QTextCursor, QIcon
#from qtrangeslider import   QLabeledDoubleRangeSlider
from superqt import QLabeledDoubleRangeSlider

from ConvMatTransform import ReadTrajectoryBrainsight, GetIDTrajectoryBrainsight,read_itk_affine_transform,itk_to_BSight,templateSlicer,BSight_to_itk

from SelFiles.SelFiles import SelFiles

import numpy as np

from matplotlib.pyplot import cm
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import (
    FigureCanvas,NavigationToolbar2QT)
import time
import yaml

import nibabel
import argparse
from pathlib import Path
from CalculateMaskProcess import CalculateMaskProcess
import platform
import ants
_IS_MAC = platform.system() == 'Darwin'

def resource_path():  # needed for bundling
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if not _IS_MAC:
        return os.path.split(Path(__file__))[0]

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundle_dir = Path(sys._MEIPASS)
    else:
        bundle_dir = Path(__file__).parent

    return bundle_dir

def get_text_values(initial_texts, parent=None, title="", label=""):
    '''
    Simple Input dialog to ask for multiple inputs
    '''
    dialog = QInputDialog()
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.show()
    # hide default QLineEdit
    dialog.findChild(QLineEdit).hide()

    editors = []
    for i, text in enumerate(initial_texts, start=1):
        editor = QLineEdit(text=text)
        dialog.layout().insertWidget(i, editor)
        editors.append(editor)

    ret = dialog.exec() == QDialog.Accepted
    return ret, [editor.text() for editor in editors]

###################################################################

class OutputWrapper(QObject):
    outputWritten = Signal(object, object)

    def __init__(self, parent, stdout=True):
        super().__init__(parent)
        if stdout:
            self._stream = sys.stdout
            sys.stdout = self
        else:
            self._stream = sys.stderr
            sys.stderr = self
        self._stdout = stdout

    def write(self, text):
        self._stream.write(text)
        self.outputWritten.emit(text, self._stdout)

    def __getattr__(self, name):
        return getattr(self._stream, name)

    def __del__(self):
        try:
            if self._stdout:
                sys.stdout = self._stream
            else:
                sys.stderr = self._stream
        except AttributeError:
            pass

#Pointers to functions

GetSmallestSOS=None

class BabelBrain(QWidget):
    '''
    Main LIFU Control application

    '''
    def __init__(self,simbnibs_path='',T1W='',Mat4Trajectory='',ThermalProfile='',bInUseWithBrainsight=False):
        super(BabelBrain, self).__init__()
        print('home',Path.home())
        #This file will store the last config selected
        self._LastSelConfig=str(Path.home())+os.sep+os.path.join('.config','BabelBrain','lastselection.yaml')

        self._BrainsightSyncPath=str(Path.home())+os.sep+'.BabelBrainSync'

        self._bInUseWithBrainsight=bInUseWithBrainsight #this will be use to sync input and output with Brainsight
        widget = SelFiles()
    
        prevConfig=self.GetLatestSelection()
        
        if prevConfig is not None:
            widget.ui.SimbNIBSlineEdit.setText(prevConfig['simbnibs_path'])
            widget.ui.T1WlineEdit.setText(prevConfig['T1W'])
            widget.ui.TrajectorylineEdit.setText(prevConfig['Mat4Trajectory'])
            widget.ui.ThermalProfilelineEdit.setText(prevConfig['ThermalProfile'])
            if 'CT_or_ZTE_input' in prevConfig:
                widget.ui.CTlineEdit.setText(prevConfig['CT_or_ZTE_input'])
                widget.ui.CTTypecomboBox.setCurrentIndex(prevConfig['CTType'])
            if 'SimbNIBSType' in prevConfig:
                SimbNIBSType=prevConfig['SimbNIBSType']
                if SimbNIBSType =='charm':
                    SimbNIBSTypeint=0
                else:
                    SimbNIBSTypeint=1
                widget.ui.SimbNIBSTypecomboBox.setCurrentIndex(SimbNIBSTypeint)
            if 'TrajectoryType' in prevConfig:
                TrajectoryType=prevConfig['TrajectoryType']
                if TrajectoryType =='brainsight':
                    TrajectoryTypeint=0
                else:
                    TrajectoryTypeint=1
                widget.ui.TrajectoryTypecomboBox.setCurrentIndex(TrajectoryTypeint)
            if 'CoregCT_MRI' in prevConfig:
                widget.ui.CoregCTcomboBox.setCurrentIndex(prevConfig['CoregCT_MRI'])
            if 'ComputingBackend' in prevConfig:
                if prevConfig['ComputingBackend']==0:
                    Backend==''
                    GPU='CPU'
                else:
                    GPU=prevConfig['ComputingDevice']
                    if prevConfig['ComputingBackend']==1:
                        Backend='CUDA'
                    elif prevConfig['ComputingBackend']==2:
                        Backend='OpenCL'
                    elif prevConfig['ComputingBackend']==3:
                        Backend='Metal'

                widget.SelectComputingEngine(GPU=GPU,Backend=Backend)

            if 'TxSystem' in prevConfig:
                widget.SelectTxSystem(prevConfig['TxSystem'])

        if bInUseWithBrainsight:
            Brainsight=self.GetInputFromBrainsight()
            assert(Brainsight is not None)
            widget.ui.SimbNIBSlineEdit.setText(Brainsight['simbnibs_path'])
            widget.ui.T1WlineEdit.setText(Brainsight['T1W'])
            widget.ui.TrajectorylineEdit.setText(Brainsight['Mat4Trajectory'])

        widget.exec()
        simbnibs_path=widget.ui.SimbNIBSlineEdit.text()
        T1W=widget.ui.T1WlineEdit.text()
        CT_or_ZTE_input=widget.ui.CTlineEdit.text()
        bUseCT=widget.ui.CTTypecomboBox.currentIndex()>0
        CTType=widget.ui.CTTypecomboBox.currentIndex()
        Mat4Trajectory=widget.ui.TrajectorylineEdit.text()
        ThermalProfile=widget.ui.ThermalProfilelineEdit.text()
        if widget.ui.SimbNIBSTypecomboBox.currentIndex()==0:
            SimbNIBSType ='charm'
        else:
            SimbNIBSType ='headreco'
        if widget.ui.TrajectoryTypecomboBox.currentIndex()==0:
            TrajectoryType ='brainsight'
        else:
            TrajectoryType ='slicer'
        
        self.Config={}
        ComputingDevice,Backend =widget.GetSelectedComputingEngine()
        if ComputingDevice=='CPU':
            ComputingBackend=0
        elif Backend=='CUDA':
            ComputingBackend=1
        elif Backend=='OpenCL':
            ComputingBackend=2
        elif Backend=='Metal':
            ComputingBackend=3

        self.Config['ComputingBackend']=ComputingBackend
        self.Config['ComputingDevice']=ComputingDevice
        self.Config['TxSystem']=widget.ui.TransducerTypecomboBox.currentText()

        self.Config['simbnibs_path']=simbnibs_path
        self.Config['SimbNIBSType']=SimbNIBSType
        self.Config['TrajectoryType']=TrajectoryType
        self.Config['Mat4Trajectory']=Mat4Trajectory
        self.Config['ThermalProfile']=ThermalProfile
        self.Config['T1W']=T1W
        self.Config['bUseCT']=bUseCT
        self.Config['CTType']=widget.ui.CTTypecomboBox.currentIndex()
        self.Config['CoregCT_MRI']=widget.ui.CoregCTcomboBox.currentIndex()
        self.Config['CT_or_ZTE_input']=CT_or_ZTE_input
        self.Config['ID'] = os.path.splitext(os.path.split(self.Config['Mat4Trajectory'])[1])[0]
        self.Config['T1WIso']= self.Config['T1W'].replace('.nii.gz','-isotropic.nii.gz')
        

        self.SaveLatestSelection()


        self.load_ui()
        self.InitApplication()
        self.static_canvas=None

    def GetInputFromBrainsight(self):
        res=None
        PathMat4Trajectory  = self._BrainsightSyncPath + os.sep +'Input_Target.txt'
        PathT1W             = self._BrainsightSyncPath + os.sep +'Input_Anatomical.txt'
        Pathsimbnibs_path   = self._BrainsightSyncPath + os.sep +'Input_SegmentationsPath.txt'


        if os.path.isfile(PathMat4Trajectory) and \
           os.path.isfile(PathT1W) and \
           os.path.isfile(Pathsimbnibs_path):
            res={}
            with open (PathT1W,'r') as f:
                l=f.readlines()[0].strip()
            res['T1W']=l

            ID=GetIDTrajectoryBrainsight(PathMat4Trajectory)
            
            #for the time being, we need the trajectory to be next to T1w
            RPath=os.path.split(res['T1W'])[0]+os.sep+ID+'.txt'
            assert(shutil.copyfile(PathMat4Trajectory,RPath))

            print('ID,RPath',ID,RPath)

            res['Mat4Trajectory']=RPath
            
            with open (Pathsimbnibs_path,'r') as f:
                l=f.readlines()[0].strip()
            res['simbnibs_path']=l
            
            if not os.path.isdir(res['simbnibs_path']) or not os.path.isfile(res['T1W']) or not os.path.isfile(res['Mat4Trajectory']):
                    print('Ignoring Brainsight config as files and dir may not exist anymore\n',res)
                    res=None
        return res

    def GetLatestSelection(self):
        res=None
        if os.path.isfile(self._LastSelConfig):
            with open(self._LastSelConfig,'r') as f:
                try:
                    res=yaml.safe_load(f)
                except BaseException as e:
                    print('Unable to load previous selection')
                    print(e)
                    res=None
            try:
                if res is not None:
                    if not os.path.isdir(res['simbnibs_path']) or not os.path.isfile(res['T1W']) or not os.path.isfile(res['Mat4Trajectory'])\
                    or not os.path.isfile(res['ThermalProfile']):
                        print('Ignoring config as files and dir may not exist anymore\n',res)
                        res=None
            except:
                res = None
        return res

    def SaveLatestSelection(self):
        if not os.path.isfile(self._LastSelConfig):
            try:
                os.makedirs(os.path.split(self._LastSelConfig)[0],exist_ok=True)
            except BaseException as e:
                print('Unable to save selection')
                print(e)
                return
        if os.path.isdir(os.path.split(self._LastSelConfig)[0]):
            with open(self._LastSelConfig,'w') as f:
                try:
                    res=yaml.safe_dump(self.Config,f)
                except BaseException as e:
                    print('Unable to save selection')
                    print(e)


    def load_ui(self):
        global GetSmallestSOS
        loader = QUiLoader()
        #path = os.fspath(Path(__file__).resolve().parent / "form.ui")
        path = os.path.join(resource_path(), "form.ui")
        ui_file = QFile(path)
        ui_file.open(QFile.ReadOnly)
        self.Widget = loader.load(ui_file, self)
        ui_file.close()
        ## THIS WILL BE LOADED DYNAMICALLY in function of the active Tx
        import BabelDatasetPreps as DataPreps

        from TranscranialModeling.BabelIntegrationBASE import GetSmallestSOS
        if self.Config['TxSystem'] =='Single':
            from Babel_SingleTx.Babel_SingleTx import SingleTx as WidgetAcSim
        elif self.Config['TxSystem'] =='CTX_500':
            from Babel_CTX500.Babel_CTX500 import CTX500 as WidgetAcSim
        elif self.Config['TxSystem'] =='H317':
            from Babel_H317.Babel_H317 import H317 as WidgetAcSim
        elif self.Config['TxSystem'] =='H246':
            from Babel_H246.Babel_H246 import H246 as WidgetAcSim
        else:
            self.EndWithError("TX system " + self.Config['TxSystem'] + " is not yet supported")

        from Babel_Thermal_SingleFocus.Babel_Thermal import Babel_Thermal as WidgetThermal

        new_tab = WidgetAcSim(parent=self.Widget.tabWidget,MainApp=self)
        grid_tab = QGridLayout(new_tab)
        grid_tab.setSpacing(1)
        new_tab.setLayout(grid_tab)
        new_tab.tab_name_private = "AcSim"
        self.Widget.tabWidget.addTab(new_tab, "Step 2 - Ac Sim")
        new_tab.setEnabled(False)
        self.AcSim=new_tab

        new_tab = WidgetThermal(parent=self.Widget.tabWidget,MainApp=self)
        grid_tab = QGridLayout(new_tab)
        grid_tab.setSpacing(1)
        new_tab.setLayout(grid_tab)
        new_tab.tab_name_private = "ThermalSim"
        self.Widget.tabWidget.addTab(new_tab, "Step 3 - Thermal Sim")
        new_tab.setEnabled(False)
        self.ThermalSim=new_tab

        slider= QLabeledDoubleRangeSlider(Qt.Orientation.Horizontal)
        slider.setRange(0.05, 1.0)
        slider.setValue((0.1, 0.6))
        ZTE=self.Widget.CTZTETabs.widget(0)
        LayRange=ZTE.findChildren(QVBoxLayout)[0]
        LayRange.addWidget(slider)
        self.Widget.ZTERangeSlider=slider
        self.Widget.setStyleSheet("QTabBar::tab::disabled {width: 0; height: 0; margin: 0; padding: 0; border: none;} ")
        if self.Config['bUseCT'] == False:
            self.Widget.CTZTETabs.hide()
        elif self.Config['CTType']!=2:
            self.Widget.CTZTETabs.setTabEnabled(0,False)
        self.Widget.HUTreshold=self.Widget.CTZTETabs.widget(1).findChildren(QDoubleSpinBox)[0]
        
    
    @Slot()
    def handleOutput(self, text, stdout):
        color = self.Widget.outputTerminal.textColor()
        self.Widget.outputTerminal.moveCursor(QTextCursor.End)
        self.Widget.outputTerminal.setTextColor(color if stdout else self._err_color)
        self.Widget.outputTerminal.insertPlainText(text)
        self.Widget.outputTerminal.setTextColor(color)

    def InitApplication(self):
        '''
        Initialization of GUI controls using configuration information

        '''
        
        self._figMasks=None
        self._figMask2=None

        while self.Widget.USMaskkHzDropDown.count()>0:
            self.Widget.USMaskkHzDropDown.removeItem(0)

        for f in self.AcSim.Config['USFrequencies']:
            print('f','%i'%(f/1e3))
            self.Widget.USMaskkHzDropDown.insertItem(0, '%i'%(f/1e3))


        self.setWindowTitle('BabelBrain - ' + self.Config['ID'] + ' - ' + self.Config['TxSystem'] +
                            ' - ' + os.path.split(self.Config['ThermalProfile'])[1].split('.yaml')[0])
        self.Widget.IDLabel.setText(self.Config['ID'])
        self.Widget.TXLabel.setText(self.Config['TxSystem'])
        self.Widget.ThermalProfileLabel.setText(os.path.split(self.Config['ThermalProfile'])[1].split('.yaml')[0])

        #we connect callbacks
        self.Widget.CalculatePlanningMask.clicked.connect(self.GenerateMask)

        self.Widget.USMaskkHzDropDown.currentIndexChanged.connect(self.UpdateParamsMaskFloat)
        self.Widget.USPPWSpinBox.valueChanged.connect(self.UpdateParamsMaskFloat)



        #Then we update the GUI and control parameters
        self.UpdateMaskParameters()

        stdout = OutputWrapper(self, True)
        stdout.outputWritten.connect(self.handleOutput)
#        stderr = OutputWrapper(self, False)
#        stderr.outputWritten.connect(self.handleOutput)

    def UpdateMaskParameters(self):
        '''
        Update of GUI elements and parameters to be used in LFIU
        '''
        self.Widget.USMaskkHzDropDown.setProperty('UserData',float(self.Widget.USMaskkHzDropDown.currentText())*1e3)

        for obj in [self.Widget.USPPWSpinBox]:
            obj.setProperty('UserData',obj.value())


    def EndWithError(self,msg):
         msgBox = QMessageBox()
         msgBox.setIcon(QMessageBox.Critical)
         msgBox.setText(msg)
         msgBox.exec()
         raise SystemError(msg)



    @Slot(float)
    def UpdateParamsMaskFloat(self, newvalue):
        self.UpdateMaskParameters()


    @Slot()
    def GenerateMask(self):
        '''
        This function will produce the mask required for simulation
        '''
        Frequency=  self.Widget.USMaskkHzDropDown.property('UserData')
        BasePPW=self.Widget.USPPWSpinBox.property('UserData')

        self._prefix= self.Config['ID'] + '_' + self.Config['TxSystem'] +'_%ikHz_%iPPW_' %(int(Frequency/1e3),BasePPW)
        self._prefix_path=os.path.dirname(self.Config['T1WIso'])+os.sep+self._prefix
        self._outnameMask=self._prefix_path+'BabelViscoInput.nii.gz'
        self._BrainsightInput=self._prefix_path+'FullElasticSolution.nii.gz'

        print('outname',self._outnameMask)

        bCalcMask=False
        if os.path.isfile(self._outnameMask):

            ret = QMessageBox.question(self,'', "Mask file already exists.\nDo you want to recalculate?\nSelect No to reload", QMessageBox.Yes | QMessageBox.No)

            if ret == QMessageBox.Yes:
                bCalcMask=True
        else:
            bCalcMask = True

        if bCalcMask:
            #We run the Backkground
            self.thread = QThread()
            self.worker = RunMaskGeneration(self)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.UpdateMask)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            
            self.worker.endError.connect(self.NotifyError)
            self.worker.endError.connect(self.thread.quit)
            self.worker.endError.connect(self.worker.deleteLater)

            self.thread.start()
            self.Widget.tabWidget.setEnabled(False)

        else:
            self.UpdateMask()

    #this will modify the coordinates of the trajectory
    def ExportTrajectory(self,CorX=0.0,CorY=0.0,CorZ=0.0):
        newFName=os.path.join(os.path.split(self.Config['Mat4Trajectory'])[0],'_mod_'+os.path.split(self.Config['Mat4Trajectory'])[1])
            
        if self.Config['TrajectoryType']=='brainsight':
            OrigTraj=ReadTrajectoryBrainsight(self.Config['Mat4Trajectory'])
            OrigTraj[0,3]+=CorX
            OrigTraj[1,3]+=CorY
            OrigTraj[2,3]+=CorZ
            with open(self.Config['Mat4Trajectory'],'r') as f:
                allLines=f.readlines()
            for n,l in enumerate(allLines):
                if l[0]!='#':
                    break
            LastLine=l.split('\t')
            LastLine[0]='_mod_'+LastLine[0]
            LastLine[1]='%4.3f' %(OrigTraj[0,3])
            LastLine[2]='%4.3f' %(OrigTraj[1,3])
            LastLine[3]='%4.3f' %(OrigTraj[2,3])
            allLines[n]='\t'.join(LastLine)
            with open(newFName,'w') as f:
                f.writelines(allLines)
        else:
            inMat=read_itk_affine_transform(self.Config['Mat4Trajectory'])
            OrigTraj = itk_to_BSight(inMat)
            OrigTraj[0,3]+=CorX
            OrigTraj[1,3]+=CorY
            OrigTraj[2,3]+=CorZ
            transform = BSight_to_itk(OrigTraj)
            outString=templateSlicer.format(m0n0=transform[0,0],
                                        m0n1=transform[1,0],
                                        m0n2=transform[2,0],
                                        m1n0=transform[0,1],
                                        m1n1=transform[1,1],
                                        m1n2=transform[2,1],
                                        m2n0=transform[0,2],
                                        m2n1=transform[1,2],
                                        m2n2=transform[2,2],
                                        X=transform[0,3],
                                        Y=transform[1,3],
                                        Z=transform[2,3])
        
            with open(newFName,'w') as f:
                f.write(outString)



    def UpdateAcousticTab(self):
        self.AcSim.NotifyGeneratedMask()

    def NotifyError(self):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Critical)
        msgBox.setText("There was an error in execution -\nconsult log window for details")
        msgBox.exec()

    def UpdateMask(self):
        '''
        Refresh mask
        '''
        self.Widget.tabWidget.setEnabled(True)
        self.AcSim.setEnabled(True)
        Data=nibabel.load(self._outnameMask)
        self._DataMask=Data
        if self.Config['bUseCT']:
            self._CTnib=nibabel.load(self._prefix_path+'CT.nii.gz')
            CTData=np.flip(self._CTnib.get_fdata(),axis=2)
        FinalMask=Data.get_fdata()
        FinalMask=np.flip(FinalMask,axis=2)
        self._FinalMask=FinalMask
        voxSize=Data.header.get_zooms()
        x_vec=np.arange(Data.shape[0])*voxSize[0]
        x_vec-=x_vec.mean()
        y_vec=np.arange(Data.shape[1])*voxSize[1]
        y_vec-=y_vec.mean()
        z_vec=np.arange(Data.shape[2])*voxSize[2]
        z_vec-=z_vec.mean()
        LocFocalPoint=np.array(np.where(FinalMask==5)).flatten()
        CMapXZ=FinalMask[:,LocFocalPoint[1],:]
        CMapYZ=FinalMask[LocFocalPoint[0],:,:]
        CMapXY=FinalMask[:,:,LocFocalPoint[2]]
        

        sr=['y:','w:']

        plt.rcParams['font.size']=8
        extentXZ=[x_vec.min(),x_vec.max(),z_vec.max(),z_vec.min()]
        extentYZ=[y_vec.min(),y_vec.max(),z_vec.max(),z_vec.min()]
        extentXY=[x_vec.min(),x_vec.max(),y_vec.max(),y_vec.min()]

        CTMaps=[None,None,None]
        if self.Config['bUseCT']:
            CTMapXZ=CTData[:,LocFocalPoint[1],:]
            CTMapYZ=CTData[LocFocalPoint[0],:,:]
            CTMapXY=CTData[:,:,LocFocalPoint[2]]
            CTMaps=[CTMapXZ,CTMapYZ,CTMapXY]

        if self._figMasks is not None:
            for im,imCT,CMap,CTMap,extent in zip(self._imMasks,self._imCtMasks,
                                    [CMapXZ,CMapYZ,CMapXY],
                                    CTMaps,
                                    [extentXZ,extentYZ,extentXY]):
                im.set_data(CMap.T)
                if CTMap is not None:
                    Zm = np.ma.masked_where((CMap !=2) &(CMap!=3) , CTMap)
                    imCT.set_data(Zm.T)
                im.set_extent(extent)
            self._figMasks.canvas.draw_idle()
        else:
            
            self._imMasks=[]
            self._imCtMasks=[]

            self._figMasks = Figure(figsize=(18, 6))

            if self.static_canvas is not None:
                self._layout.removeItem(self._layout.itemAt(0))
                self._layout.removeItem(self._layout.itemAt(0))
            else:
                self._layout = QVBoxLayout(self.Widget.USMask)

            self.static_canvas = FigureCanvas(self._figMasks)
            
            toolbar=NavigationToolbar2QT(self.static_canvas,self)
            self._layout.addWidget(toolbar)
            self._layout.addWidget(self.static_canvas)

            axes=self.static_canvas.figure.subplots(1,3)

            for CMap,CTMap,extent,static_ax,vec1,vec2,c1,c2 in zip([CMapXZ,CMapYZ,CMapXY],
                                    CTMaps,
                                    [extentXZ,extentYZ,extentXY],
                                    axes,
                                    [x_vec,y_vec,x_vec],
                                    [z_vec,z_vec,y_vec],
                                    [LocFocalPoint[0],LocFocalPoint[1],LocFocalPoint[0]],
                                    [LocFocalPoint[2],LocFocalPoint[2],LocFocalPoint[1]]):


                self._imMasks.append(static_ax.imshow(CMap.T,cmap=cm.jet,extent=extent,aspect='equal'))
                if CTMap is not None:
                    Zm = np.ma.masked_where((CMap !=2) &(CMap!=3) , CTMap)
                    self._imCtMasks.append(static_ax.imshow(Zm.T,cmap=cm.gray,extent=extent,aspect='equal'))
                else:
                    self._imCtMasks.append(None)
                    XX,ZZ=np.meshgrid(vec1,vec2)
                    static_ax.contour(XX,ZZ,CMap.T,[0,1,2,3], cmap=plt.cm.gray)

                static_ax.plot(vec1[c1],vec2[c2],'+y',markersize=14)
            self._figMasks.set_facecolor(np.array(self.palette().color(QPalette.Window).getRgb())/255)

        self.UpdateAcousticTab()

    def GetExport(self):
        ExtraConfig ={}
        ExtraConfig['PPW']=self.Widget.USPPWSpinBox.property('UserData')
        if self.Config['bUseCT']:
            ExtraConfig['HUThreshold']=self.Widget.HUTreshold.value()
            if self.Config['CTType']==2 : #ZTE
                ExtraConfig['ZTERange']=self.Widget.ZTERangeSlider.value()
        return self.Config | ExtraConfig

class RunMaskGeneration(QObject):

    finished = Signal()
    endError = Signal()

    def __init__(self,mainApp):
        super(RunMaskGeneration, self).__init__()
        self._mainApp=mainApp

    def run(self):
        """Long-running task."""

        print("*"*40)
        print("*"*5+" Calculating mask.. BE PATIENT... it can take a couple of minutes...")
        print("*"*40)

        deviceName=self._mainApp.Config['ComputingDevice']
        COMPUTING_BACKEND=self._mainApp.Config['ComputingBackend']

        Widget=self._mainApp.Widget

        T1WIso= self._mainApp.Config['T1WIso']
        T1W= self._mainApp.Config['T1W']

        Frequency=  Widget.USMaskkHzDropDown.property('UserData')
        SmallestSoS= GetSmallestSOS(Frequency,bShear=True)

        BasePPW=Widget.USPPWSpinBox.property('UserData')
        SpatialStep=np.round(SmallestSoS/Frequency/BasePPW*1e3,3) #step of mask to reconstruct , mm
        print("Frequency, SmallestSoS, BasePPW,SpatialStep",Frequency, SmallestSoS, BasePPW,SpatialStep)

        prefix=self._mainApp._prefix
        print("Config['Mat4Trajectory']",self._mainApp.Config['Mat4Trajectory'])

        #first we ensure we have isotropic scans at 1 mm required to get affine matrix at 1.0 mm isotropic
        preT1=ants.image_read(T1W)
        preT1.set_spacing([1.0,1.0,1.0])
        ants.image_write(preT1,T1WIso)

        kargs={}
        kargs['SimbNIBSDir']=self._mainApp.Config['simbnibs_path']
        kargs['SimbNIBSType']=self._mainApp.Config['SimbNIBSType']
        kargs['CoregCT_MRI']=self._mainApp.Config['CoregCT_MRI']
        kargs['TrajectoryType']=self._mainApp.Config['TrajectoryType']
        kargs['Mat4Trajectory']=self._mainApp.Config['Mat4Trajectory'] #Path to trajectory file
        kargs['T1Conformal_nii']=T1WIso
        kargs['nIterationsAlign']=10
        kargs['SpatialStep']=SpatialStep
        kargs['InitialAligment']='HF'
        kargs['Location']=[0,0,0] #This coordinate will be ignored
        kargs['prefix']=prefix
        kargs['bPlot']=False
        kargs['bAlignToSkin']=True
        
        if self._mainApp.Config['bUseCT']:
            kargs['CT_or_ZTE_input']=self._mainApp.Config['CT_or_ZTE_input']
            kargs['bIsZTE']=self._mainApp.Config['CTType']==2
            if kargs['bIsZTE']:
                kargs['ZTERange']=self._mainApp.Widget.ZTERangeSlider.value()
            kargs['HUThreshold']=self._mainApp.Widget.HUTreshold.value()
        # Start mask generation as separate process.
        queue=Queue()
        maskWorkerProcess = Process(target=CalculateMaskProcess, 
                                    args=(queue,
                                         COMPUTING_BACKEND,
                                         deviceName),
                                    kwargs=kargs)
        maskWorkerProcess.start()      
        # progress.
        T0=time.time()
        bNoError=True
        while maskWorkerProcess.is_alive():
            time.sleep(0.1)
            while queue.empty() == False:
                cMsg=queue.get()
                print(cMsg,end='')
                if '--Babel-Brain-Low-Error' in cMsg:
                    bNoError=False

        maskWorkerProcess.join()
        while queue.empty() == False:
            cMsg=queue.get()
            print(cMsg,end='')
            if '--Babel-Brain-Low-Error' in cMsg:
                bNoError=False
        if bNoError:
            TEnd=time.time()
            print('Total time',TEnd-T0)
            print("*"*40)
            print("*"*5+" DONE calculating mask.")
            print("*"*40)
            self.finished.emit()
        else:
            print("*"*40)
            print("*"*5+" Error in execution.")
            print("*"*40)
            self.endError.emit()

def main():

    if os.getenv('FSLDIR') is None:
        os.environ['FSLDIR']='/usr/local/fsl'
        os.environ['FSLOUTPUTTYPE']='NIFTI_GZ'
        os.environ['PATH']=os.environ['PATH']+':'+'/usr/local/fsl/bin'

    class MyParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)
    
    parser = MyParser(prog='BabelBrain', usage='python %(prog)s.py [options]',description='Run BabelBrain simulation',  formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--Mat4Trajectory', type=str, nargs='?',default='',help='Path to Brainsight trajectory file')
    parser.add_argument('--T1W', type=str, nargs='?',default='',help='Path to T1W Nifti file')
    parser.add_argument('--simbnibs_path', type=str, nargs='?',default='',help='Path to Simbnibs output dir')
    parser.add_argument('--ThermalProfile', type=str, nargs='?',default='',help='Path to thermal profile file')
    parser.add_argument('-bInUseWithBrainsight', action='store_true')

    args = parser.parse_args()
    app = QApplication([])
    icon = QIcon(os.path.join(resource_path(),'Proteus-Alciato-logo.png'))
    app.setWindowIcon(icon)
    widget = BabelBrain(Mat4Trajectory=args.Mat4Trajectory,
                        T1W=args.T1W,
                        simbnibs_path=args.simbnibs_path,
                        ThermalProfile=args.ThermalProfile,
                        bInUseWithBrainsight=args.bInUseWithBrainsight)
    widget.show()
    sys.exit(app.exec())

if __name__ == "__main__":

    main()
