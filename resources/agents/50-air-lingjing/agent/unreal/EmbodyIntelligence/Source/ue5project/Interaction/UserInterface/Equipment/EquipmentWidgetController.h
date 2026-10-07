// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Equipment/EquipmentStruct.h"

/**
 *
 */


class AEquipmentActor;

enum class EActiveEquipmentPanel : uint8
{
	None,
	Drone,
	Car,
	Dog
};


class UE5PROJECT_API FEquipmentWidgetController
{
public:
	static FEquipmentWidgetController* Get();
	
	EActiveEquipmentPanel GetActivePanel() const;

protected:
	void SwitchPanel(EActiveEquipmentPanel InPanel);
	EActiveEquipmentPanel ActivePanel = EActiveEquipmentPanel::None;
	FString ActiveEquipmentId;

	TSharedPtr<SWidget> EquipmentWidget;

public:
	DECLARE_DELEGATE_OneParam(FOnEquipmentInfoUpdate, const FEquipmentInfo& /* EquipmentInfo */);
	DECLARE_DELEGATE_OneParam(FOnEquipmentTransformUpdate, const FTransform& /* Transform */);
	DECLARE_DELEGATE_OneParam(FOnTrajectoryPointAdded, const FVector2D&);
	DECLARE_DELEGATE_TwoParams(FOnCommandAdded, const FString&, const FString&);

	FOnEquipmentInfoUpdate OnEquipmentInfoUpdateDelegate;
	void UpdateEquipmentInfo(const FEquipmentInfo& InInfo);
	FOnEquipmentTransformUpdate OnEquipmentTransformUpdateDelegate;
	void UpdateTransform(const FTransform& InTransform) const;
	FOnTrajectoryPointAdded OnTrajectoryPointAddedDelegate;
	void AddTrajectoryPoint(const FString& InEquipmentId, const FVector2D& InPoint) const;
	FOnCommandAdded OnCommandAddedDelegate;
	void AddCommand(const FString& InEquipmentId, const FString& InType, const FString& InContent) const;
	
	
	
	void CreateEquipmentWidget(const FString& InEquipmentId);
	void RemoveEquipmentWidget();
	
protected:
	void CreateDroneWidget(AEquipmentActor* InEquipmentActor);
	void CreateCarWidget(AEquipmentActor* InEquipmentActor);
	void CreateDogWidget(AEquipmentActor* InEquipmentActor);



};
