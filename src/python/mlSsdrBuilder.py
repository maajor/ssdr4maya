# -*- coding: utf-8 -*
"""
 SSDR4Maya
  Implementaion of "Smooth Skin Decomposition with Rigid Bones" for Maya 2016
  
  Reference:
    - Binh Huy Le and Zhigang Deng, Smooth Skinning Decomposition with Rigid Bones, ACM Transactions on Graphics, 31(6), 199:1--199:10, 2012.
    - Binh Huy Le and Zhigang Deng, Robust and Accurate Skeletal Rigging from Mesh Sequences, ACM Transactions on Graphics,33(4), 84:1--84:10, 2014.
"""

__author__ = "Tomohiko Mukai <contact@mukai-lab.org>"
__status__ = "alpha release"
__version_ = "0.2"
__date__ = "24 Sep 2016"
 
import sys
import math
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import maya.cmds as cmds
import maya.mel
import ssdr

def maya_useNewAPI():
    pass

def initializePlugin(plugin):
    fnPlugin = om.MFnPlugin(plugin, vendor = 'Mukai Lab.', version = '0.2')
    try:
        fnPlugin.registerCommand(ssdrBuildCmd.commandName, ssdrBuildCmd.creator)
    except:
        sys.stderr.write('Failed to register command: {0}\n'.format(ssdrBuildCmd.commandName))
        raise

    cmds.setParent('MayaWindow')
    if not cmds.menu('MukaiLab', query=True, exists=True):
        cmds.menu('MukaiLab', label='MukaiLab')
    cmds.setParent('MukaiLab', menu=True)
    if not cmds.menu('SSDR', query=True, exists=True):
        wd = ssdrUIWindow()
        cmds.menuItem('SSDR', command=wd.showWindow)

def uninitializePlugin(plugin):
    fnPlugin = om.MFnPlugin(plugin)
    try:
        fnPlugin.deregisterCommand(ssdrBuildCmd.commandName)
    except:
        sys.stderr.write('Failed to unregister command: {0}\n'.format(ssdrBuildCmd.commandName))
        raise
    cmds.deleteUI('MayaWindow|MukaiLab|SSDR', menuItem=True)

class ssdrUIWindow():

    def __init__(self):
        self.bones = 50
        self.iteration = 20
        self.influence = 8

    def generate(self, value):
        self.bones = cmds.intField(self.bn, query=True, value=True)
        self.iteration = cmds.intField(self.it, query=True, value=True)
        self.influence = cmds.intField(self.inf, query=True, value=True)
        command = "ssdrBuild %d %d %d" % (self.bones, self.iteration, self.influence)
        print command
        maya.mel.eval(command)

    def showWindow(self, plugin):
        cmds.window(title='Test Window')
        column = cmds.columnLayout()
        cmds.separator( height=10)
        cmds.rowLayout(nc=2, columnWidth2=(100, 100))
        cmds.text( label='Bones' )
        self.bn = cmds.intField('Bones', value = 50)
        cmds.setParent(column)
        cmds.separator( height=10)
        cmds.rowLayout(nc=2, columnWidth2=(100, 100))
        cmds.text( label='Iteraion' )
        self.it = cmds.intField('Iteraion', value = 20)
        cmds.setParent(column)
        cmds.separator( height=10)
        cmds.rowLayout(nc=2, columnWidth2=(100, 100))
        cmds.text( label='MaxInfluenceBones' )
        self.inf = cmds.intField('MaxInfluenceBones',  value = 8)
        cmds.setParent(column)
        cmds.separator( height=10)
        cmds.button(label="Generate!", width=200, c=self.generate)
        cmds.showWindow()

class ssdrBuildCmd(om.MPxCommand):
    commandName = 'ssdrBuild'

    def __init__(self):
        om.MPxCommand.__init__(self)

    @staticmethod
    def creator():
        return ssdrBuildCmd()

    def doIt(self, args):
        # 最小ボーン数
        # - 指定した数以上のボーンは必ず利用される。また、ボーン数は基本的に2のべき乗になることが多い
        # 　（例： numBones=10 としたときは、10より大きい2のべき乗=2^4=16となることが多い）
        self.numMinBones = args.asInt(0)
        # 計算反復回数は、ボーン数に応じて適当に設定。
        # あまり回数を増やしてもさほど影響は生じないことが多い。
        self.numMaxIterations = args.asInt(1)
        # 各頂点あたりの最大インフルーエンス数
        self.numMaxInfluences = args.asInt(2)

        # メッシュの取得
        dagPath = om.MGlobal.getActiveSelectionList().getDagPath(0)
        meshFn = om.MFnMesh(dagPath)
        if meshFn is None:
            raise
        
        # 変換時間範囲の取得
        startTime = oma.MAnimControl.animationStartTime()
        endTime = oma.MAnimControl.animationEndTime()
        numFrames = int((endTime - startTime).asUnits(om.MTime.uiUnit())) + 1
        oma.MAnimControl.setCurrentTime(startTime)

        # 先頭フレームの形状(world座標系)をバインド姿勢として登録
        points = meshFn.getPoints(om.MSpace.kWorld)
        numVertices = len(points)
        bindVertices = []
        for p in points:
            bindVertices += [p.x, p.y, p.z]

        # 変換対象シェイプアニメーションの取得
        time = om.MTime(startTime)
        animVertices = []
        while time <= endTime:
            oma.MAnimControl.setCurrentTime(time)
            points = meshFn.getPoints(om.MSpace.kWorld)
            for p in points:
                animVertices += [p.x, p.y, p.z]
            time += 1
        # ひとまず先頭フレームに移動
        oma.MAnimControl.setCurrentTime(startTime)
        # SSDR本体 : 戻り値は平方根平均二乗誤差（RMSE）
        rmse = ssdr.build(self.numMinBones, self.numMaxInfluences, self.numMaxIterations, bindVertices, animVertices, numVertices, numFrames)
        # 推定されたボーン数
        numBones = ssdr.getNumBones()
        om.MGlobal.displayInfo('RMSE = ' + str(rmse) + ', #Bones = ' + str(numBones))
        # C++モジュール内部に格納されているスキンウェイトとボーンインデクスの情報を取得
        #  [頂点1のウェイト1, 頂点1のウェイト2, ..., 頂点2のウェイト1, ... , 頂点Nのウェイト1, ... , ] のような並び
        #  ボーンインデクスも同じ並び
        skinningWeight = ssdr.getSkinningWeight()
        skinningIndex = ssdr.getSkinningIndex()

        # 複製されるメッシュの名前を適当に指定
        newSkinName = 'SsdrMesh'
        # メッシュの複製
        cmds.duplicate(meshFn.name(), returnRootsOnly=True, name=newSkinName)

        # 複製されたシェイプに紐付けるボーン群を生成
        # 
        # ボーンのリスト
        bones = []
        for b in range(numBones):
            cmds.select(d=True)
            # ボーン名は適当な接頭辞＋番号
            bone = cmds.joint(name='SsdrBone{0}'.format(b + 1))
            # ニュートラル状態（先頭フレーム）におけるボーンの姿勢をC++モジュールから取得
            #  平行移動
            t = ssdr.getBoneTranslation(b, 0)
            #  回転クォータニオン
            q = ssdr.getBoneRotation(b, 0)
            u = om.MQuaternion(q[0], q[1], q[2], q[3])
            e = u.asEulerRotation()
            cmds.move(t[0], t[1], t[2], bone, relative=False)
            cmds.rotate(e.x, e.y, e.z, bone, relative=False)
            # リストに追加
            bones.append(bone)
        # 複製メッシュとボーン群をグループ化
        newGroup = cmds.group(newSkinName, bones, name='SsdrResult')

        # スキンクラスタの生成
        ssdrRig = cmds.skinCluster(bones, newSkinName, maximumInfluences=self.numMaxInfluences, name='skinClusterSsdr')[0]
        # スキンクラスタとスキンメッシュの取得
        skinNode = om.MGlobal.getSelectionListByName(ssdrRig).getDependNode(0)
        skinFn = oma.MFnSkinCluster(skinNode)
        meshPath = om.MGlobal.getSelectionListByName(newSkinName).getDagPath(0)

        # 全頂点を対象にスキニング情報を更新
        indices = om.MIntArray(numVertices, 0)
        for i in xrange(len(indices)):
            indices[i] = i
        singleIndexedComp = om.MFnSingleIndexedComponent()
        vertexComp = singleIndexedComp.create(om.MFn.kMeshVertComponent)
        singleIndexedComp.addElements(indices)
        # インフルエンスオブジェクトの情報
        infDags = skinFn.influenceObjects()
        numInfluences = len(infDags)
        infIndices = om.MIntArray(numInfluences, 0)
        for i in xrange(numInfluences):
            infIndices[i] = i
        # ウェイトの設定
        weights = om.MDoubleArray(numVertices * numInfluences, 0)
        for v in xrange(numVertices):
            for i in xrange(self.numMaxInfluences):
                weights[v * numInfluences + skinningIndex[v * self.numMaxInfluences + i]] = skinningWeight[v * self.numMaxInfluences + i]
        skinFn.setWeights(meshPath, vertexComp, infIndices, weights)

        # ボーンモーションを設定
        startTime = cmds.playbackOptions(min=True, query=True)
        for f in range(numFrames):
            frame = startTime + f
            for b in range(numBones):
                t = ssdr.getBoneTranslation(b, f)
                q = ssdr.getBoneRotation(b, f)
                u = om.MQuaternion(q[0], q[1], q[2], q[3])
                e = u.asEulerRotation()
                cmds.setKeyframe(bones[b], t=frame, at='tx', v=t[0])
                cmds.setKeyframe(bones[b], t=frame, at='ty', v=t[1])
                cmds.setKeyframe(bones[b], t=frame, at='tz', v=t[2])
                cmds.setKeyframe(bones[b], t=frame, at='rx', v=math.degrees(e.x))
                cmds.setKeyframe(bones[b], t=frame, at='ry', v=math.degrees(e.y))
                cmds.setKeyframe(bones[b], t=frame, at='rz', v=math.degrees(e.z))
