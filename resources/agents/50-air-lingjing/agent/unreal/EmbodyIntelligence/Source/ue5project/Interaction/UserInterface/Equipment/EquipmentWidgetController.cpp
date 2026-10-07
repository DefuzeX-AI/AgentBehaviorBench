// Fill out your copyright notice in the Description page of Project Settings.


#include "EquipmentWidgetController.h"

#include "SDroneWidget.h"
#include "SCarWidget.h"
#include "SDogWidget.h"
#include "ue5project/Interaction/UserInterface/MainWidgetController.h"
#include "ue5project/Scene/Equipment/EquipmentActor.h"
#include "ue5project/Scene/Equipment/FEquipmentController.h"

FEquipmentWidgetController* FEquipmentWidgetController::Get()
{
	static FEquipmentWidgetController Instance;
	return &Instance;
}

void FEquipmentWidgetController::AddTrajectoryPoint(const FString& InEquipmentId, const FVector2D& InPoint) const
{
	if (OnTrajectoryPointAddedDelegate.IsBound())
	{
		OnTrajectoryPointAddedDelegate.Execute(InPoint);
	}
}

void FEquipmentWidgetController::AddCommand(const FString& InEquipmentId, const FString& InType,
                                            const FString& InContent) const
{
	if (OnCommandAddedDelegate.IsBound())
	{
		OnCommandAddedDelegate.Execute(InType, InContent);
	}
}

void FEquipmentWidgetController::CreateEquipmentWidget(const FString& InEquipmentId)
{
	RemoveEquipmentWidget();
	if (AEquipmentActor* EquipmentActor = FEquipmentController::Get()->GetEquipment(InEquipmentId))
	{
		const FEquipmentInfo&& EquipmentInfo = EquipmentActor->GetEquipmentInfo();
		switch (EquipmentInfo.Type)
		{
		case EEquipmentType::Drone:
			CreateDroneWidget(EquipmentActor);
			break;
		case EEquipmentType::Car:
			CreateCarWidget(EquipmentActor);
			break;
		case EEquipmentType::Dog:
			CreateDogWidget(EquipmentActor);
			break;
		case EEquipmentType::Ship:
			break;
		default: ;
		}
	}
}

void FEquipmentWidgetController::RemoveEquipmentWidget()
{
	if (EquipmentWidget.IsValid())
	{
		FMainWidgetController::Get()->RemoveWidget(EquipmentWidget.ToSharedRef());
		EquipmentWidget.Reset();
	}
}

void FEquipmentWidgetController::CreateDroneWidget(AEquipmentActor* InEquipmentActor)
{
	UTextureRenderTarget2D* FrontRenderTarget = InEquipmentActor->GetFrontRenderTarget();
	UTextureRenderTarget2D* TopdownRenderTarget = InEquipmentActor->GetTopdownRenderTarget();
	FMainWidgetController::Get()->AddWidget()
	[
		SAssignNew(EquipmentWidget, SDroneWidget)
		.FrontRenderTarget(FrontRenderTarget)
		.TopdownRenderTarget(TopdownRenderTarget)
		.Visibility(EVisibility::SelfHitTestInvisible)
	];
}

void FEquipmentWidgetController::CreateCarWidget(AEquipmentActor* InEquipmentActor)
{
	UTextureRenderTarget2D* FrontRenderTarget = InEquipmentActor->GetFrontRenderTarget();
	FMainWidgetController::Get()->AddWidget()
	[
		SAssignNew(EquipmentWidget, SCarWidget)
		.FrontRenderTarget(FrontRenderTarget)
		.Visibility(EVisibility::SelfHitTestInvisible)
	];
}

void FEquipmentWidgetController::CreateDogWidget(AEquipmentActor* InEquipmentActor)
{
	UTextureRenderTarget2D* FrontRenderTarget = InEquipmentActor->GetFrontRenderTarget();
	FMainWidgetController::Get()->AddWidget()
	[
		SAssignNew(EquipmentWidget, SDogWidget)
		.FrontRenderTarget(FrontRenderTarget)
		.Visibility(EVisibility::SelfHitTestInvisible)
	];
}

EActiveEquipmentPanel FEquipmentWidgetController::GetActivePanel() const
{
	return ActivePanel;
}

void FEquipmentWidgetController::SwitchPanel(EActiveEquipmentPanel InPanel)
{
	ActivePanel = InPanel;
	ActiveEquipmentId.Empty();
}

void FEquipmentWidgetController::UpdateEquipmentInfo(const FEquipmentInfo& InInfo)
{
	ActiveEquipmentId = InInfo.EquipmentId;

	if (OnEquipmentInfoUpdateDelegate.IsBound())
	{
		OnEquipmentInfoUpdateDelegate.Execute(InInfo);
	}
}

void FEquipmentWidgetController::UpdateTransform(const FTransform& InTransform) const
{
	if (OnEquipmentTransformUpdateDelegate.IsBound())
	{
		OnEquipmentTransformUpdateDelegate.Execute(InTransform);
	}
}
