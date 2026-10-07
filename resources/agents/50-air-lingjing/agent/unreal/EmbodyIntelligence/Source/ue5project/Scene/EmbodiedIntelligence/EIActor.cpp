// Fill out your copyright notice in the Description page of Project Settings.


#include "EIActor.h"

#include "Components/WidgetComponent.h"
#include "ue5project/Interaction/UserInterface/SpaceWidget/TagWidget.h"
#include "ue5project/Interaction/Scene/CameraController.h"


AEIActor::AEIActor()
{
	PrimaryActorTick.bCanEverTick = true;
	
	SceneComponent = CreateDefaultSubobject<USceneComponent>(TEXT("SceneComponent"));
	RootComponent = SceneComponent;
	WidgetComponent = CreateDefaultSubobject<UWidgetComponent>(TEXT("WidgetComponent"));
	WidgetComponent->SetupAttachment(RootComponent);
	SAssignNew(TagWidget, STagWidget);
	WidgetComponent->SetSlateWidget(TagWidget);
	WidgetComponent->SetWidgetSpace(EWidgetSpace::Screen);
	WidgetComponent->SetPivot(FVector2D(0.0, 1.0));
	WidgetComponent->SetDrawSize(FVector2D(160.0, 33.0));
}

void AEIActor::UpdateCameraTarget()
{
	FCameraController::Get()->FocusOn(this);
}

void AEIActor::InitTagWidget(const FSColor& InColor, const FString& InId) const
{
	if (TagWidget.IsValid())
	{
		TagWidget->SetColor(InColor);
		TagWidget->SetTagName(InId);
	}
}





