// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "LGameMode.generated.h"

UCLASS()
class UE5PROJECT_API ALGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ALGameMode();

	virtual void BeginPlay() override;

};
