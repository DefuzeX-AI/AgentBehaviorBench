// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EquipmentStruct.h"
#include "ue5project/Core/LDataStruct.h"
#include "ue5project/Net/MessageHelper/PhotoRequest/LPhotoRequestStruct.h"
#include "ue5project/Scene/EmbodiedIntelligence/EIActor.h"
#include "EquipmentActor.generated.h"

class ATaskPointActor;
class FLUploader;
class FLCapture;

UCLASS()
class UE5PROJECT_API AEquipmentActor : public AEIActor
{
	GENERATED_BODY()

public:
	AEquipmentActor();
protected:
	virtual void BeginPlay() override;


public:
	/* Equipment */
	virtual void InitEquipment(const FEquipmentInfo& InEquipmentInfo);
	FEquipmentInfo GetEquipmentInfo() const;
protected:
	UPROPERTY(BlueprintReadOnly)
	FEquipmentInfo EquipmentInfo;

	/* Photo Task */
public:
	UFUNCTION(BlueprintImplementableEvent)
	void BlueprintInit();

	UFUNCTION(BlueprintImplementableEvent)
	UTextureRenderTarget2D* GetFrontRenderTarget();
	UFUNCTION(BlueprintImplementableEvent)
	UTextureRenderTarget2D* GetTopdownRenderTarget();

	UFUNCTION(BlueprintImplementableEvent)
	void ExecuteTakePhotoTask(const FPhotoTaskInfo& InTaskInfo);
	UFUNCTION(BlueprintCallable)
	void Capture(const FPhotoTaskInfo& InTaskInfo, USceneCaptureComponent2D* CaptureComponent, const int32 SizeX, const int32 SizeY);
	void ExecuteCapture(const FCaptureInfo& InCaptureInfo);
	void OnCaptureComplete(const FCaptureInfo& InCaptureInfo);
	void OnUploadComplete(const bool bSucceed, const FString& InMessage, const TSharedPtr<FLUploader>& InUploader) const;

protected:
	FString GetImageSaveDir() const;



	virtual FSColor GetTagWidgetColor() const;
	virtual FString GetImageSaveSubdir() const;

	TArray<FCaptureInfo> CaptureList;
	int32 PhotoTaskIndex = 0;

	UFUNCTION(BlueprintCallable)
	void SwitchCameraTarget();

	UPROPERTY(BlueprintReadOnly)
	UTextureRenderTarget2D* FrontRenderTarget;
	UPROPERTY(BlueprintReadOnly)
	UTextureRenderTarget2D* TopdownRenderTarget;


	/* Transform */
	UFUNCTION(BlueprintCallable)
	void SnapGround();
public:
	FVector TraceLocation(const FVector& InLocation) const;

	UFUNCTION(BlueprintImplementableEvent)
	void UpdateDroneTransform(const FTransform& InTransform);
	UFUNCTION(BlueprintImplementableEvent)
	void UpdateCarTransform(const FTransform& InTransform);
	UFUNCTION(BlueprintImplementableEvent)
	void UpdateDogTransform(const FTransform& InTransform, const FDogJoint& InDogJoint);


	UFUNCTION(BlueprintImplementableEvent)
	void SetEquipmentScale(const FVector& InScale);

};
