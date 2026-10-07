// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ue5project/Static/Slate/InheritedtStruct.h"
#include "EIActor.generated.h"

class STagWidget;
class UWidgetComponent;

UCLASS()
class UE5PROJECT_API AEIActor : public AActor
{
	GENERATED_BODY()

public:
	AEIActor();
	
	void UpdateCameraTarget();

protected:
	UPROPERTY()
	USceneComponent* SceneComponent;
	UPROPERTY()
	UWidgetComponent* WidgetComponent;
	TSharedPtr<STagWidget> TagWidget;
	
	void InitTagWidget(const FSColor& InColor, const FString& InId) const;
	
};
